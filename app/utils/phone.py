"""Phone number normalization for the contacts address book.

Caller IDs from Twilio arrive in E.164 (``+15551234567``), but people typing
contacts into the admin UI or a CSV use many formats. We normalize to E.164 for
storage so lookups are consistent, defaulting bare 10-digit numbers to US (+1).
"""

import re

_DIGITS_RE = re.compile(r"\d")


def normalize_phone(raw):
    """Return an E.164 phone string, or None if it cannot be normalized.

    Rules:
    - Keep a leading ``+`` if present; strip all other non-digits.
    - A ``+`` followed by 7-15 digits is accepted as-is.
    - A bare 10-digit number is assumed US and becomes ``+1`` + digits.
    - A bare 11-digit number starting with ``1`` becomes ``+`` + digits.
    - Anything else is rejected (returns None).
    """
    if raw is None:
        return None
    text = str(raw).strip()
    if not text:
        return None

    has_plus = text.startswith("+")
    digits = "".join(_DIGITS_RE.findall(text))
    if not digits:
        return None

    if has_plus:
        if digits[0] == "0":
            return None
        if 7 <= len(digits) <= 15:
            return f"+{digits}"
        return None

    if len(digits) == 10:
        return f"+1{digits}"
    if len(digits) == 11 and digits[0] == "1":
        return f"+{digits}"
    return None


def last_ten(phone):
    """Return the last 10 digits of a phone number, for loose US matching."""
    if not phone:
        return ""
    digits = "".join(_DIGITS_RE.findall(str(phone)))
    return digits[-10:] if len(digits) >= 10 else digits
