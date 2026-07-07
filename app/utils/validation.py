"""Input sanitization and validation helpers.

Server-side validation is authoritative; client-side HTML constraints are only
defense-in-depth. Every value that arrives from a browser form, a URL/query
param, or a Twilio webhook body is treated as untrusted.
"""

import re

from app.utils.ssml import normalize_ivr_ssml

# Characters below 0x20 (control chars) plus DEL. We strip these from all text
# input; they have no place in caller IDs, settings, or spoken prompts.
_CONTROL_CHARS_RE = re.compile(r"[\x00-\x1f\x7f]")


def sanitize_text(value, max_length=None):
    """Trim whitespace, drop control characters, and enforce an optional cap.

    Returns a clean string. If ``max_length`` is given, the result is truncated
    as a defense-in-depth safety net (form validators reject over-length input
    before this is reached).
    """
    if value is None:
        return ""
    text = str(value)
    text = _CONTROL_CHARS_RE.sub("", text)
    text = text.strip()
    if max_length is not None and len(text) > max_length:
        text = text[:max_length]
    return text


def sanitize_ivr_text(value, max_length=500):
    """Sanitize IVR prompt text, allowing a small whitelist of SSML tags.

    Unknown tags are stripped and allowed SSML attributes are normalized.
    """
    if value is None:
        return ""
    text = normalize_ivr_ssml(str(value))
    return sanitize_text(text, max_length=max_length)


def parse_positive_int(value, min_value=1, max_value=None, default=None):
    """Parse ``value`` into an int within [min_value, max_value] or return default.

    Used for identifiers where out-of-range or unparseable input should be
    rejected (caller decides how, e.g. a 404).
    """
    try:
        number = int(str(value).strip())
    except (TypeError, ValueError):
        return default
    if number < min_value:
        return default
    if max_value is not None and number > max_value:
        return default
    return number


def clamp_int(value, default, min_value, max_value):
    """Parse ``value`` into an int, clamping to [min_value, max_value].

    Used for pagination where invalid input should fall back to a sane default
    rather than error out.
    """
    try:
        number = int(str(value).strip())
    except (TypeError, ValueError):
        return default
    return max(min_value, min(number, max_value))


def safe_next_url(next_param):
    """Return ``next_param`` only if it is a safe relative admin path.

    Blocks open redirects: absolute URLs, scheme-relative ``//host`` paths, and
    backslash tricks are all rejected. Only paths under ``/admin`` are allowed.
    """
    if not next_param:
        return None
    if not next_param.startswith("/"):
        return None
    if next_param.startswith("//") or "\\" in next_param:
        return None
    if not next_param.startswith("/admin"):
        return None
    return next_param


# Explicit entity map so quotes are escaped too (attribute-safe), not just the
# minimal set handled by the stdlib.
_TWIML_ESCAPES = {
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&apos;",
}


def escape_for_twiml(text):
    """XML-escape a raw string for safe embedding in hand-built TwiML/XML.

    Note: the Twilio TwiML library escapes element text on its own, so this must
    not be applied to values passed through ``VoiceResponse`` helpers (it would
    double-escape). It exists for any place that assembles XML strings directly.
    """
    if text is None:
        return ""
    result = str(text)
    result = result.replace("&", "&amp;")
    for char, entity in _TWIML_ESCAPES.items():
        if char == "&":
            continue
        result = result.replace(char, entity)
    return result
