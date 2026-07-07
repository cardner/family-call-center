"""Outbound SMS notifications for new voicemails.

When a recording is saved, an SMS alert is sent to each number configured in the
admin Settings UI (stored in the SQLite ``settings`` table, not the environment).
Sending is best-effort: per-recipient failures are logged, never raised, so a
failed text can never lose a recording or break the Twilio callback.
"""

import logging

from app.utils.settings import get_notify_phone_numbers
from config import Config

logger = logging.getLogger(__name__)

# SMS bodies over this length are truncated; Twilio would otherwise split long
# messages into multiple billed segments.
_SMS_BODY_MAX_LENGTH = 320


def _default_client_factory():
    from twilio.rest import Client

    return Client(Config.TWILIO_ACCOUNT_SID, Config.TWILIO_AUTH_TOKEN)


def mask_phone(number):
    """Mask a phone number for display, keeping only the last four digits."""
    if not number:
        return ""
    if len(number) <= 4:
        return "…" + number
    return "…" + number[-4:]


def message_admin_url(message_id):
    """Return the admin deep link for a saved message."""
    return f"{Config.BASE_URL}/admin/messages/{message_id}"


def format_sms_body(caller_id, duration, message_id):
    """Build the SMS text for a new voicemail alert."""
    caller = caller_id or "unknown"
    body = (
        f"New voicemail from {caller} ({duration}s). "
        f"Listen: {message_admin_url(message_id)}"
    )
    return body[:_SMS_BODY_MAX_LENGTH]


def _send_sms(to, body, client_factory=None):
    """Send a single SMS. Returns a per-recipient result dict."""
    client_factory = client_factory or _default_client_factory
    try:
        client = client_factory()
        client.messages.create(body=body, from_=Config.TWILIO_PHONE_NUMBER, to=to)
        logger.info("Sent SMS notification to %s", mask_phone(to))
        return {"to": to, "status": "sent", "detail": None}
    except Exception as exc:  # noqa: BLE001 - surface any Twilio/client error
        logger.warning(
            "Could not send SMS notification to %s", mask_phone(to), exc_info=True
        )
        return {"to": to, "status": "failed", "detail": str(exc)}


def _send_to_all(body, client_factory=None):
    recipients = get_notify_phone_numbers()
    if not recipients:
        return []
    return [_send_sms(to, body, client_factory=client_factory) for to in recipients]


def notify_new_message(
    *, message_id, caller_id, duration, created_at=None, client_factory=None
):
    """Send a new-voicemail SMS to every configured recipient.

    Best-effort: returns per-recipient results and never raises. An empty list
    means notifications are disabled (no recipients configured).
    """
    body = format_sms_body(caller_id, duration, message_id)
    return _send_to_all(body, client_factory=client_factory)


def send_test_notification(client_factory=None):
    """Send a test SMS to every configured recipient, using a synthetic body."""
    body = (
        "Test alert from your family call center. "
        f"SMS notifications are working. {Config.BASE_URL}/admin"
    )
    return _send_to_all(body, client_factory=client_factory)


def notification_summary():
    """Return notification status for the admin UI.

    Phone numbers are masked so full numbers never appear in rendered HTML.
    """
    recipients = get_notify_phone_numbers()
    return {
        "enabled": bool(recipients),
        "recipient_count": len(recipients),
        "masked_recipients": [mask_phone(number) for number in recipients],
    }
