"""Editable IVR/voicemail settings stored in the SQLite ``settings`` table.

These replace the previously hardcoded prompt strings so they can be edited from
the admin UI. Infrastructure secrets (Twilio creds, BASE_URL, DATA_DIR) are NOT
stored here — they remain environment-only.
"""

import re

from app.utils.db import get_connection

# Speech/prompt fields are capped to this many characters.
IVR_TEXT_MAX_LENGTH = 500

# Recording length bounds (seconds).
MAX_RECORDING_SECONDS_MIN = 10
MAX_RECORDING_SECONDS_MAX = 600

# The SMS notification recipient field accepts a handful of numbers; cap the raw
# text to keep the settings row bounded.
NOTIFY_PHONE_NUMBERS_MAX_LENGTH = 500

# Twilio only transcribes recordings shorter than this many seconds; when
# transcription is on we clamp the Record verb's max length to it.
TRANSCRIPTION_MAX_RECORDING_SECONDS = 120

# E.164: a leading +, a nonzero leading digit, then up to 14 more digits.
_E164_RE = re.compile(r"^\+[1-9]\d{6,14}$")

# How a blocked caller is handled at /call. ``reject`` returns a busy signal
# with no audio; ``message`` plays the configured prompt and hangs up.
BLOCK_ACTIONS = ("reject", "message")

DEFAULT_SETTINGS = {
    "greeting": 'Welcome. <break time="300ms"/>',
    "invalid_digit_message": (
        "I didn't catch that. <break time=\"200ms\"/> Please try again."
    ),
    "voicemail_prompt": (
        "Please leave your message after the beep. <break time=\"300ms\"/> "
        'Press <emphasis level="moderate">pound</emphasis> when you are finished.'
    ),
    "voicemail_thanks": (
        'Thank you. <break time="200ms"/> Your message has been saved. Goodbye.'
    ),
    "max_recording_seconds": "300",
    "ivr_voice": "Google.en-US-Neural2-D",
    "notify_phone_numbers": "",
    "transcription_enabled": "false",
    "personalized_greeting_enabled": "false",
    "block_action": "reject",
    "blocked_caller_message": (
        "This number is not accepting calls. <break time=\"200ms\"/> Goodbye."
    ),
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


def is_transcription_enabled():
    """Return True if voicemail transcription is turned on in Settings."""
    return get_setting("transcription_enabled", "false") == "true"


def is_personalized_greeting_enabled():
    """Return True if personalized greetings are turned on in Settings."""
    return get_setting("personalized_greeting_enabled", "false") == "true"


def get_block_action():
    """Return the configured blocked-caller action, defaulting to ``reject``."""
    action = get_setting("block_action", DEFAULT_SETTINGS["block_action"])
    return action if action in BLOCK_ACTIONS else DEFAULT_SETTINGS["block_action"]


def is_valid_e164(number):
    """Return True if ``number`` is a plausible E.164 phone number."""
    return bool(_E164_RE.match(number or ""))


def parse_phone_numbers(raw):
    """Split a raw recipients string into individual tokens.

    Accepts commas and newlines as separators. Whitespace is trimmed and empty
    tokens are dropped. Order is preserved and duplicates are removed.
    """
    if not raw:
        return []
    tokens = re.split(r"[,\n]", str(raw))
    numbers = []
    for token in tokens:
        cleaned = token.strip()
        if cleaned and cleaned not in numbers:
            numbers.append(cleaned)
    return numbers


def get_notify_phone_numbers():
    """Return the stored SMS recipients, keeping only valid E.164 numbers.

    Invalid entries are skipped defensively so a bad value can never break the
    voicemail callback; the settings form rejects invalid input on save.
    """
    raw = get_setting("notify_phone_numbers", DEFAULT_SETTINGS["notify_phone_numbers"])
    return [number for number in parse_phone_numbers(raw) if is_valid_e164(number)]
