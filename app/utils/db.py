import logging
import os
import sqlite3
from datetime import datetime, timezone

from config import Config

logger = logging.getLogger(__name__)

DB_PATH = os.path.join(Config.DATA_DIR, "ivr.db")


def get_connection():
    os.makedirs(Config.DATA_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _utcnow_iso():
    return datetime.now(timezone.utc).isoformat()


def init_db():
    with get_connection() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS recordings (
                id                INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at        TEXT    NOT NULL,
                caller_id         TEXT,
                duration          INTEGER,
                filename          TEXT    NOT NULL,
                file_size         INTEGER,
                twilio_sid        TEXT,
                transcript        TEXT,
                transcript_status TEXT    NOT NULL DEFAULT 'disabled',
                read_at           TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key   TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS contacts (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                phone         TEXT    NOT NULL UNIQUE,
                display_name  TEXT    NOT NULL,
                is_vip        INTEGER NOT NULL DEFAULT 0,
                email         TEXT    NOT NULL DEFAULT '',
                is_admin      INTEGER NOT NULL DEFAULT 0,
                is_parent     INTEGER NOT NULL DEFAULT 0,
                box_id        INTEGER,
                created_at    TEXT    NOT NULL,
                updated_at    TEXT    NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS blocked_numbers (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                phone      TEXT    NOT NULL UNIQUE,
                note       TEXT,
                source     TEXT    NOT NULL DEFAULT 'user',
                created_at TEXT    NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS voicemail_boxes (
                id                   INTEGER PRIMARY KEY AUTOINCREMENT,
                slug                 TEXT    NOT NULL UNIQUE,
                display_name         TEXT    NOT NULL,
                extension_digit      TEXT    NOT NULL UNIQUE,
                voicemail_prompt     TEXT    NOT NULL DEFAULT '',
                voicemail_thanks     TEXT    NOT NULL DEFAULT '',
                notify_phone_numbers TEXT    NOT NULL DEFAULT '',
                is_child             INTEGER NOT NULL DEFAULT 0,
                enabled              INTEGER NOT NULL DEFAULT 1,
                sort_order           INTEGER NOT NULL DEFAULT 0
            )
        """)
        # Links a parent contact to the child mailbox(es) they are notified for.
        conn.execute("""
            CREATE TABLE IF NOT EXISTS parent_child_links (
                contact_id INTEGER NOT NULL,
                box_id     INTEGER NOT NULL,
                PRIMARY KEY (contact_id, box_id)
            )
        """)
        _migrate_db(conn)
        conn.commit()

    # Seed default settings and voicemail boxes after the tables exist. Imported
    # here to avoid a circular import (both modules depend on this one).
    from app.utils.boxes import seed_default_boxes
    from app.utils.settings import seed_default_settings

    seed_default_settings()
    seed_default_boxes()


def _column_names(conn, table):
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return {row["name"] for row in rows}


def _migrate_db(conn):
    """Apply idempotent schema upgrades to pre-existing databases.

    ``CREATE TABLE IF NOT EXISTS`` covers fresh installs; these ``ALTER TABLE``
    statements bring older databases (created before transcription, read/unread,
    and contacts existed) up to the current schema without data loss.
    """
    recording_columns = _column_names(conn, "recordings")
    if "transcript" not in recording_columns:
        conn.execute("ALTER TABLE recordings ADD COLUMN transcript TEXT")
    if "transcript_status" not in recording_columns:
        conn.execute(
            "ALTER TABLE recordings ADD COLUMN transcript_status TEXT "
            "NOT NULL DEFAULT 'disabled'"
        )
    if "read_at" not in recording_columns:
        conn.execute("ALTER TABLE recordings ADD COLUMN read_at TEXT")
    if "box_id" not in recording_columns:
        conn.execute("ALTER TABLE recordings ADD COLUMN box_id INTEGER")

    contact_columns = _column_names(conn, "contacts")
    # The VIP flag used to be called ``skip_ivr_menu``; it now only bypasses the
    # blocklist (VIPs still choose a mailbox from the menu). Rename in place on
    # older databases, or add it to pre-VIP databases that never had it.
    if "is_vip" not in contact_columns:
        if "skip_ivr_menu" in contact_columns:
            conn.execute("ALTER TABLE contacts RENAME COLUMN skip_ivr_menu TO is_vip")
        else:
            conn.execute(
                "ALTER TABLE contacts ADD COLUMN is_vip INTEGER NOT NULL DEFAULT 0"
            )

    # Email notification fields (added when SMS alerts were replaced by email).
    if "email" not in contact_columns:
        conn.execute("ALTER TABLE contacts ADD COLUMN email TEXT NOT NULL DEFAULT ''")
    if "is_admin" not in contact_columns:
        conn.execute(
            "ALTER TABLE contacts ADD COLUMN is_admin INTEGER NOT NULL DEFAULT 0"
        )
    # Parent accounts are emailed for the child mailboxes they are linked to.
    if "is_parent" not in contact_columns:
        conn.execute(
            "ALTER TABLE contacts ADD COLUMN is_parent INTEGER NOT NULL DEFAULT 0"
        )
    if "box_id" not in contact_columns:
        conn.execute("ALTER TABLE contacts ADD COLUMN box_id INTEGER")

    # A voicemail box can be flagged as a "child" mailbox; messages there also
    # notify the parent accounts linked to it via ``parent_child_links``.
    box_columns = _column_names(conn, "voicemail_boxes")
    if "is_child" not in box_columns:
        conn.execute(
            "ALTER TABLE voicemail_boxes ADD COLUMN is_child INTEGER NOT NULL DEFAULT 0"
        )
    # A voicemail box maps to at most one contact. A partial UNIQUE index allows
    # many contacts with no box (NULL) while still preventing duplicate links.
    conn.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_contacts_box_id "
        "ON contacts(box_id) WHERE box_id IS NOT NULL"
    )


def log_recording(
    created_at,
    caller_id,
    duration,
    filename,
    file_size,
    twilio_sid,
    transcript_status="disabled",
    box_id=None,
):
    """Insert a recording row and return its new id."""
    with get_connection() as conn:
        cursor = conn.execute(
            """
            INSERT INTO recordings (
                created_at, caller_id, duration, filename, file_size,
                twilio_sid, transcript_status, box_id
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                created_at,
                caller_id,
                duration,
                filename,
                file_size,
                twilio_sid,
                transcript_status,
                box_id,
            ),
        )
        conn.commit()
        return cursor.lastrowid


def _search_clause(search):
    """Build the WHERE fragment and params for a recordings search.

    Matches the caller ID, the transcript text, or a linked contact's display
    name (via a LEFT JOIN on contacts.phone = recordings.caller_id).
    """
    like = f"%{search}%"
    clause = "(r.caller_id LIKE ? OR r.transcript LIKE ? OR c.display_name LIKE ?)"
    return clause, [like, like, like]


def _recording_filters(search, unread_only, box_id):
    conditions = []
    params = []
    if search:
        clause, clause_params = _search_clause(search)
        conditions.append(clause)
        params.extend(clause_params)
    if unread_only:
        conditions.append("r.read_at IS NULL")
    if box_id is not None:
        conditions.append("r.box_id = ?")
        params.append(box_id)
    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    return where, params


def count_recordings(search=None, unread_only=False, box_id=None):
    where, params = _recording_filters(search, unread_only, box_id)
    with get_connection() as conn:
        row = conn.execute(
            f"""
            SELECT COUNT(*) AS n
            FROM recordings r
            LEFT JOIN contacts c ON c.phone = r.caller_id
            {where}
            """,
            params,
        ).fetchone()
        return row["n"] if row else 0


def list_recordings(limit=50, offset=0, search=None, unread_only=False, box_id=None):
    where, params = _recording_filters(search, unread_only, box_id)
    with get_connection() as conn:
        rows = conn.execute(
            f"""
            SELECT r.*, b.display_name AS box_name, b.slug AS box_slug
            FROM recordings r
            LEFT JOIN contacts c ON c.phone = r.caller_id
            LEFT JOIN voicemail_boxes b ON b.id = r.box_id
            {where}
            ORDER BY datetime(r.created_at) DESC, r.id DESC
            LIMIT ? OFFSET ?
            """,
            params + [limit, offset],
        ).fetchall()
        return rows


def get_recording(recording_id):
    with get_connection() as conn:
        return conn.execute(
            "SELECT * FROM recordings WHERE id = ?", (recording_id,)
        ).fetchone()


def get_recording_by_twilio_sid(twilio_sid):
    with get_connection() as conn:
        return conn.execute(
            "SELECT * FROM recordings WHERE twilio_sid = ?", (twilio_sid,)
        ).fetchone()


def update_recording_transcript(recording_id, transcript, status):
    with get_connection() as conn:
        conn.execute(
            "UPDATE recordings SET transcript = ?, transcript_status = ? WHERE id = ?",
            (transcript, status, recording_id),
        )
        conn.commit()


def mark_recording_read(recording_id):
    """Mark a recording read if it is not already. Returns True if it changed."""
    with get_connection() as conn:
        cursor = conn.execute(
            "UPDATE recordings SET read_at = ? WHERE id = ? AND read_at IS NULL",
            (_utcnow_iso(), recording_id),
        )
        conn.commit()
        return cursor.rowcount > 0


def mark_all_recordings_read():
    """Mark every unread recording as read. Returns the number updated."""
    with get_connection() as conn:
        cursor = conn.execute(
            "UPDATE recordings SET read_at = ? WHERE read_at IS NULL",
            (_utcnow_iso(),),
        )
        conn.commit()
        return cursor.rowcount


def count_unread_recordings():
    with get_connection() as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS n FROM recordings WHERE read_at IS NULL"
        ).fetchone()
        return row["n"] if row else 0


def delete_recording(recording_id):
    """Delete a recording row and its audio file.

    Returns True if a row was deleted. The file is removed best-effort; a missing
    file is logged but not treated as a failure.
    """
    row = get_recording(recording_id)
    if row is None:
        return False

    with get_connection() as conn:
        conn.execute("DELETE FROM recordings WHERE id = ?", (recording_id,))
        conn.commit()

    _delete_recording_file(row["filename"])
    return True


def _delete_recording_file(filename):
    """Remove the recording file, guarding against path traversal.

    ``filename`` is a relative path stored in the DB (e.g. ``2026/07/05/x.wav``).
    The resolved absolute path must stay inside RECORDINGS_DIR.
    """
    if not filename:
        return
    recordings_root = os.path.realpath(Config.RECORDINGS_DIR)
    target = os.path.realpath(os.path.join(recordings_root, filename))
    if not target.startswith(recordings_root + os.sep):
        logger.warning("Refusing to delete file outside recordings dir: %s", filename)
        return
    try:
        os.remove(target)
        logger.info("Deleted recording file %s", target)
    except FileNotFoundError:
        logger.warning("Recording file already missing: %s", target)
    except OSError:
        logger.warning("Could not delete recording file %s", target, exc_info=True)


# --- Contacts ---------------------------------------------------------------


def count_contacts():
    with get_connection() as conn:
        row = conn.execute("SELECT COUNT(*) AS n FROM contacts").fetchone()
        return row["n"] if row else 0


def list_contacts(limit=100, offset=0):
    with get_connection() as conn:
        return conn.execute(
            """
            SELECT * FROM contacts
            ORDER BY display_name COLLATE NOCASE ASC, id ASC
            LIMIT ? OFFSET ?
            """,
            (limit, offset),
        ).fetchall()


def all_contacts():
    """Return every contact, used to build the phone -> name lookup map."""
    with get_connection() as conn:
        return conn.execute("SELECT * FROM contacts").fetchall()


def get_contact(contact_id):
    with get_connection() as conn:
        return conn.execute(
            "SELECT * FROM contacts WHERE id = ?", (contact_id,)
        ).fetchone()


def get_contact_by_phone(phone):
    with get_connection() as conn:
        return conn.execute(
            "SELECT * FROM contacts WHERE phone = ?", (phone,)
        ).fetchone()


def upsert_contact(
    phone,
    display_name,
    is_vip=False,
    email="",
    is_admin=False,
    box_id=None,
    is_parent=False,
):
    """Insert or update a contact keyed on the normalized phone number."""
    now = _utcnow_iso()
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO contacts (
                phone, display_name, is_vip, email, is_admin, is_parent,
                box_id, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(phone) DO UPDATE SET
                display_name = excluded.display_name,
                is_vip       = excluded.is_vip,
                email        = excluded.email,
                is_admin     = excluded.is_admin,
                is_parent    = excluded.is_parent,
                box_id       = excluded.box_id,
                updated_at   = excluded.updated_at
            """,
            (
                phone,
                display_name,
                1 if is_vip else 0,
                email or "",
                1 if is_admin else 0,
                1 if is_parent else 0,
                box_id,
                now,
                now,
            ),
        )
        conn.commit()


def list_admin_contacts():
    """Return contacts flagged as admins (they receive Family mailbox alerts)."""
    with get_connection() as conn:
        return conn.execute(
            "SELECT * FROM contacts WHERE is_admin = 1 "
            "ORDER BY display_name COLLATE NOCASE ASC, id ASC"
        ).fetchall()


def set_parent_child_links(contact_id, box_ids):
    """Replace the child-mailbox links for a parent contact."""
    with get_connection() as conn:
        conn.execute(
            "DELETE FROM parent_child_links WHERE contact_id = ?", (contact_id,)
        )
        seen = set()
        for box_id in box_ids or ():
            if box_id is None or box_id in seen:
                continue
            seen.add(box_id)
            conn.execute(
                "INSERT INTO parent_child_links (contact_id, box_id) VALUES (?, ?)",
                (contact_id, box_id),
            )
        conn.commit()


def get_parent_child_box_ids(contact_id):
    """Return the child-mailbox ids a parent contact is linked to."""
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT box_id FROM parent_child_links WHERE contact_id = ?",
            (contact_id,),
        ).fetchall()
    return [row["box_id"] for row in rows]


def get_parent_contacts_for_box(box_id):
    """Return the parent contacts linked to a child mailbox."""
    if box_id is None:
        return []
    with get_connection() as conn:
        return conn.execute(
            """
            SELECT c.* FROM contacts c
            JOIN parent_child_links l ON l.contact_id = c.id
            WHERE l.box_id = ?
            ORDER BY c.display_name COLLATE NOCASE ASC, c.id ASC
            """,
            (box_id,),
        ).fetchall()


def get_contact_by_box_id(box_id):
    """Return the contact linked to a voicemail box, or None."""
    if box_id is None:
        return None
    with get_connection() as conn:
        return conn.execute(
            "SELECT * FROM contacts WHERE box_id = ?", (box_id,)
        ).fetchone()


def list_notification_contacts():
    """Return contacts that can receive email alerts (admin, parent, or box-linked)."""
    with get_connection() as conn:
        return conn.execute(
            "SELECT * FROM contacts "
            "WHERE (is_admin = 1 OR is_parent = 1 OR box_id IS NOT NULL) "
            "AND email <> '' "
            "ORDER BY display_name COLLATE NOCASE ASC, id ASC"
        ).fetchall()


def delete_contact(contact_id):
    with get_connection() as conn:
        conn.execute(
            "DELETE FROM parent_child_links WHERE contact_id = ?", (contact_id,)
        )
        cursor = conn.execute("DELETE FROM contacts WHERE id = ?", (contact_id,))
        conn.commit()
        return cursor.rowcount > 0


def bulk_upsert_contacts(rows):
    """Upsert many (phone, display_name, email) rows. Returns the count written.

    The admin and box-link fields are intentionally left untouched here so a CSV
    re-import never clears notification settings configured in the UI.
    """
    now = _utcnow_iso()
    written = 0
    with get_connection() as conn:
        for phone, display_name, email in rows:
            conn.execute(
                """
                INSERT INTO contacts (phone, display_name, email, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(phone) DO UPDATE SET
                    display_name = excluded.display_name,
                    email        = excluded.email,
                    updated_at   = excluded.updated_at
                """,
                (phone, display_name, email or "", now, now),
            )
            written += 1
        conn.commit()
    return written


# --- Blocked numbers --------------------------------------------------------


def count_blocked():
    with get_connection() as conn:
        row = conn.execute("SELECT COUNT(*) AS n FROM blocked_numbers").fetchone()
        return row["n"] if row else 0


def count_blocked_by_source(source):
    with get_connection() as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS n FROM blocked_numbers WHERE source = ?", (source,)
        ).fetchone()
        return row["n"] if row else 0


def list_blocked(limit=100, offset=0):
    with get_connection() as conn:
        return conn.execute(
            """
            SELECT * FROM blocked_numbers
            ORDER BY datetime(created_at) DESC, id DESC
            LIMIT ? OFFSET ?
            """,
            (limit, offset),
        ).fetchall()


def all_blocked():
    """Return every blocked number, used to build the lookup index."""
    with get_connection() as conn:
        return conn.execute("SELECT * FROM blocked_numbers").fetchall()


def get_blocked(blocked_id):
    with get_connection() as conn:
        return conn.execute(
            "SELECT * FROM blocked_numbers WHERE id = ?", (blocked_id,)
        ).fetchone()


def get_blocked_by_phone(phone):
    with get_connection() as conn:
        return conn.execute(
            "SELECT * FROM blocked_numbers WHERE phone = ?", (phone,)
        ).fetchone()


def upsert_blocked(phone, note=None, source="user"):
    """Insert or update a single blocked number keyed on the normalized phone.

    An existing row (e.g. from an imported seed) has its note and source
    overwritten, so a manual block always wins and survives seed removal.
    """
    now = _utcnow_iso()
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO blocked_numbers (phone, note, source, created_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(phone) DO UPDATE SET
                note   = excluded.note,
                source = excluded.source
            """,
            (phone, note, source, now),
        )
        conn.commit()


def delete_blocked(blocked_id):
    with get_connection() as conn:
        cursor = conn.execute(
            "DELETE FROM blocked_numbers WHERE id = ?", (blocked_id,)
        )
        conn.commit()
        return cursor.rowcount > 0


def delete_blocked_by_source(source):
    """Delete every blocked number with the given source. Returns the count."""
    with get_connection() as conn:
        cursor = conn.execute(
            "DELETE FROM blocked_numbers WHERE source = ?", (source,)
        )
        conn.commit()
        return cursor.rowcount


def bulk_upsert_blocked(entries):
    """Insert many (phone, note, source) blocked entries.

    Existing numbers are left untouched (so manually blocked numbers keep their
    ``user`` source). Returns the number of rows actually inserted.
    """
    now = _utcnow_iso()
    added = 0
    with get_connection() as conn:
        for phone, note, source in entries:
            cursor = conn.execute(
                """
                INSERT INTO blocked_numbers (phone, note, source, created_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(phone) DO NOTHING
                """,
                (phone, note, source, now),
            )
            added += cursor.rowcount
        conn.commit()
    return added
