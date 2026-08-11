"""Editable IVR/voicemail settings stored in the SQLite ``settings`` table.

These replace the previously hardcoded prompt strings so they can be edited from
the admin UI. Infrastructure secrets (Twilio creds, BASE_URL, DATA_DIR) are NOT
stored here — they remain environment-only.
"""

import ipaddress
import re

from app.utils.db import get_connection
from app.utils.settings_crypto import (
    decrypt_setting_value,
    encrypt_setting_value,
    encryption_available,
    is_encrypted_value,
)

# Speech/prompt fields are capped to this many characters.
IVR_TEXT_MAX_LENGTH = 500

# Recording length bounds (seconds).
MAX_RECORDING_SECONDS_MIN = 10
MAX_RECORDING_SECONDS_MAX = 600

# SMTP text fields (host, username, from address) are capped to keep the
# settings row bounded.
SMTP_TEXT_MAX_LENGTH = 255

# Ports we allow for Fastmail SMTP submission: 465 (implicit SSL) or 587
# (STARTTLS). Anything else is rejected on save.
SMTP_ALLOWED_PORTS = (465, 587)

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
    "transcription_enabled": "false",
    "personalized_greeting_enabled": "false",
    "block_action": "reject",
    "blocked_caller_message": (
        "This number is not accepting calls. <break time=\"200ms\"/> Goodbye."
    ),
}

# Fastmail SMTP settings. Stored in the same ``settings`` table but always
# encrypted at rest and accessed only through the ``*_smtp_*`` helpers below, so
# they are deliberately kept out of DEFAULT_SETTINGS (which seeds plaintext rows
# and is exposed by get_all_settings).
SMTP_DEFAULTS = {
    "smtp_host": "smtp.fastmail.com",
    "smtp_port": "465",
    "smtp_user": "",
    "smtp_password": "",
    "smtp_from": "",
}
SMTP_SETTING_KEYS = tuple(SMTP_DEFAULTS)


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
    """Return all non-secret settings.

    SMTP credentials are deliberately excluded: they are encrypted at rest and
    must be read individually through ``get_smtp_setting`` so decrypted secrets
    never flow into general-purpose settings consumers or rendered pages.
    """
    with get_connection() as conn:
        rows = conn.execute("SELECT key, value FROM settings").fetchall()
    values = dict(DEFAULT_SETTINGS)
    for row in rows:
        if row["key"] in SMTP_SETTING_KEYS:
            continue
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


# --- Fastmail SMTP settings (encrypted at rest) ----------------------------


def is_valid_smtp_host(host):
    """Return True if ``host`` is a safe, routable SMTP hostname.

    Rejects URLs, embedded ports, and literal private/reserved IP addresses so
    the admin-configurable host cannot be used to reach internal services
    (SSRF). A bare hostname must have at least two DNS labels.
    """
    host = (host or "").strip()
    if not host or len(host) > SMTP_TEXT_MAX_LENGTH:
        return False
    if any(ch in host for ch in " /\\:@\t\r\n"):
        return False
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        pass
    else:
        return not (
            ip.is_private
            or ip.is_loopback
            or ip.is_reserved
            or ip.is_link_local
            or ip.is_multicast
            or ip.is_unspecified
        )
    labels = host.split(".")
    if len(labels) < 2:
        return False
    label_re = re.compile(r"^[A-Za-z0-9]([A-Za-z0-9-]{0,61}[A-Za-z0-9])?$")
    return all(label_re.match(label) for label in labels)


def normalize_smtp_port(value):
    """Return a valid SMTP port (465 or 587), defaulting to 465."""
    try:
        port = int(value)
    except (TypeError, ValueError):
        return int(SMTP_DEFAULTS["smtp_port"])
    return port if port in SMTP_ALLOWED_PORTS else int(SMTP_DEFAULTS["smtp_port"])


def get_smtp_setting(key):
    """Return one decrypted SMTP setting, falling back to its default.

    Legacy plaintext values (written before encryption existed) are returned
    as-is and get re-encrypted the next time the field is saved.
    """
    if key not in SMTP_SETTING_KEYS:
        raise KeyError(key)
    with get_connection() as conn:
        row = conn.execute(
            "SELECT value FROM settings WHERE key = ?", (key,)
        ).fetchone()
    if row is None:
        return SMTP_DEFAULTS[key]
    raw = row["value"]
    if is_encrypted_value(raw):
        plain = decrypt_setting_value(raw)
        return plain if plain is not None else ""
    return raw


def set_smtp_setting(key, plaintext):
    """Encrypt and persist one SMTP setting. Raises if no key is configured."""
    if key not in SMTP_SETTING_KEYS:
        raise KeyError(key)
    set_setting(key, encrypt_setting_value("" if plaintext is None else str(plaintext)))


def get_smtp_config():
    """Return the decrypted SMTP configuration used to send email."""
    host = get_smtp_setting("smtp_host") or SMTP_DEFAULTS["smtp_host"]
    user = get_smtp_setting("smtp_user")
    from_email = get_smtp_setting("smtp_from") or user
    return {
        "host": host,
        "port": normalize_smtp_port(get_smtp_setting("smtp_port")),
        "user": user,
        "password": get_smtp_setting("smtp_password"),
        "from_email": from_email,
    }


def smtp_configured():
    """Return True if email can actually be sent right now."""
    if not encryption_available():
        return False
    config = get_smtp_config()
    return bool(
        config["host"]
        and config["user"]
        and config["password"]
        and config["from_email"]
    )
