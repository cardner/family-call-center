import logging
import os
import sqlite3

from config import Config

logger = logging.getLogger(__name__)

DB_PATH = os.path.join(Config.DATA_DIR, "ivr.db")


def get_connection():
    os.makedirs(Config.DATA_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with get_connection() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS recordings (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at  TEXT    NOT NULL,
                caller_id   TEXT,
                duration    INTEGER,
                filename    TEXT    NOT NULL,
                file_size   INTEGER,
                twilio_sid  TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key   TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
        """)
        conn.commit()

    # Seed default settings after the tables exist. Imported here to avoid a
    # circular import (settings.py depends on this module).
    from app.utils.settings import seed_default_settings

    seed_default_settings()


def log_recording(created_at, caller_id, duration, filename, file_size, twilio_sid):
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO recordings (created_at, caller_id, duration, filename, file_size, twilio_sid)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (created_at, caller_id, duration, filename, file_size, twilio_sid),
        )
        conn.commit()


def count_recordings(caller_filter=None):
    with get_connection() as conn:
        if caller_filter:
            row = conn.execute(
                "SELECT COUNT(*) AS n FROM recordings WHERE caller_id LIKE ?",
                (f"%{caller_filter}%",),
            ).fetchone()
        else:
            row = conn.execute("SELECT COUNT(*) AS n FROM recordings").fetchone()
        return row["n"] if row else 0


def list_recordings(limit=50, offset=0, caller_filter=None):
    with get_connection() as conn:
        if caller_filter:
            rows = conn.execute(
                """
                SELECT * FROM recordings
                WHERE caller_id LIKE ?
                ORDER BY datetime(created_at) DESC, id DESC
                LIMIT ? OFFSET ?
                """,
                (f"%{caller_filter}%", limit, offset),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT * FROM recordings
                ORDER BY datetime(created_at) DESC, id DESC
                LIMIT ? OFFSET ?
                """,
                (limit, offset),
            ).fetchall()
        return rows


def get_recording(recording_id):
    with get_connection() as conn:
        return conn.execute(
            "SELECT * FROM recordings WHERE id = ?", (recording_id,)
        ).fetchone()


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
