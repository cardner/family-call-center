"""Editable IVR/voicemail settings stored in the SQLite ``settings`` table.

These replace the previously hardcoded prompt strings so they can be edited from
the admin UI. Infrastructure secrets (Twilio creds, BASE_URL, DATA_DIR) are NOT
stored here — they remain environment-only.
"""

from app.utils.db import get_connection

# Speech/prompt fields are capped to this many characters.
IVR_TEXT_MAX_LENGTH = 500

# Recording length bounds (seconds).
MAX_RECORDING_SECONDS_MIN = 10
MAX_RECORDING_SECONDS_MAX = 600

DEFAULT_SETTINGS = {
    "greeting": "Welcome. Press 1 to leave a voicemail.",
    "invalid_digit_message": "I didn't catch that. Press 1 to leave a voicemail.",
    "voicemail_prompt": (
        "Please leave your voicemail after the beep. "
        "Press pound when you are finished."
    ),
    "voicemail_thanks": "Thank you. Your message has been saved. Goodbye.",
    "max_recording_seconds": "300",
}


def seed_default_settings():
    """Insert any missing default settings without overwriting existing values."""
    with get_connection() as conn:
        for key, value in DEFAULT_SETTINGS.items():
            conn.execute(
                "INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)",
                (key, value),
            )
        conn.commit()


def get_setting(key, default=None):
    with get_connection() as conn:
        row = conn.execute(
            "SELECT value FROM settings WHERE key = ?", (key,)
        ).fetchone()
    if row is not None:
        return row["value"]
    if default is not None:
        return default
    return DEFAULT_SETTINGS.get(key)


def set_setting(key, value):
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO settings (key, value) VALUES (?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
            """,
            (key, str(value)),
        )
        conn.commit()


def get_all_settings():
    with get_connection() as conn:
        rows = conn.execute("SELECT key, value FROM settings").fetchall()
    values = dict(DEFAULT_SETTINGS)
    for row in rows:
        values[row["key"]] = row["value"]
    return values


def get_max_recording_seconds():
    """Return the configured max recording length as a bounded integer."""
    raw = get_setting("max_recording_seconds", DEFAULT_SETTINGS["max_recording_seconds"])
    try:
        seconds = int(raw)
    except (TypeError, ValueError):
        seconds = int(DEFAULT_SETTINGS["max_recording_seconds"])
    return max(MAX_RECORDING_SECONDS_MIN, min(seconds, MAX_RECORDING_SECONDS_MAX))
