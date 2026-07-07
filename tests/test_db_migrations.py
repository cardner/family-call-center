from app.utils.db import _column_names, _migrate_db, get_connection, init_db


def test_recordings_has_new_columns():
    with get_connection() as conn:
        cols = _column_names(conn, "recordings")
    assert {"transcript", "transcript_status", "read_at"} <= cols


def test_contacts_table_exists():
    with get_connection() as conn:
        cols = _column_names(conn, "contacts")
    assert {"phone", "display_name", "skip_ivr_menu", "created_at", "updated_at"} <= cols


def test_blocked_numbers_table_exists():
    with get_connection() as conn:
        cols = _column_names(conn, "blocked_numbers")
    assert {"phone", "note", "source", "created_at"} <= cols


def test_migrate_adds_skip_ivr_menu_to_legacy_contacts():
    # Recreate the pre-VIP contacts schema, then confirm migration adds the column.
    with get_connection() as conn:
        conn.execute("DROP TABLE contacts")
        conn.execute(
            """
            CREATE TABLE contacts (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                phone        TEXT    NOT NULL UNIQUE,
                display_name TEXT    NOT NULL,
                created_at   TEXT    NOT NULL,
                updated_at   TEXT    NOT NULL
            )
            """
        )
        conn.commit()

        assert "skip_ivr_menu" not in _column_names(conn, "contacts")

        _migrate_db(conn)
        conn.commit()

        cols = _column_names(conn, "contacts")

    assert "skip_ivr_menu" in cols


def test_init_db_is_idempotent():
    init_db()
    init_db()
    with get_connection() as conn:
        cols = _column_names(conn, "recordings")
    assert "transcript" in cols


def test_migrate_upgrades_legacy_recordings_table():
    # Recreate the pre-transcription schema, then confirm migration adds columns.
    with get_connection() as conn:
        conn.execute("DROP TABLE recordings")
        conn.execute(
            """
            CREATE TABLE recordings (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at  TEXT    NOT NULL,
                caller_id   TEXT,
                duration    INTEGER,
                filename    TEXT    NOT NULL,
                file_size   INTEGER,
                twilio_sid  TEXT
            )
            """
        )
        conn.commit()

        assert "transcript" not in _column_names(conn, "recordings")

        _migrate_db(conn)
        conn.commit()

        cols = _column_names(conn, "recordings")

    assert {"transcript", "transcript_status", "read_at"} <= cols
