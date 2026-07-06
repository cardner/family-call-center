import re


def valid_settings(**overrides):
    """Return a complete, valid settings form payload with optional overrides."""
    data = {
        "greeting": "Hello there.",
        "invalid_digit_message": "Try again please.",
        "voicemail_prompt": "Leave a message after the beep.",
        "voicemail_thanks": "Thank you, goodbye.",
        "max_recording_seconds": "200",
    }
    data.update(overrides)
    return data


def extract_csrf(html):
    """Pull the csrf_token value out of a rendered form."""
    match = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html)
    return match.group(1) if match else None
