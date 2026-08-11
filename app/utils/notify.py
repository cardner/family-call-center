"""Outbound email notifications for new voicemails.

When a recording is saved, an email alert is sent through Fastmail SMTP to the
recipients derived from the Contacts address book: the Family mailbox notifies
every admin contact, and each personal mailbox notifies the single contact
linked to it. SMTP settings live (encrypted) in the admin Settings UI.

Sending is best-effort: per-recipient failures are logged, never raised, so a
failed email can never lose a recording or break the Twilio callback.
"""

import logging
import smtplib
from email.message import EmailMessage

from app.utils.contacts import (
    get_all_notification_emails,
    mask_email,
    resolve_email_recipients,
)
from app.utils.settings import get_smtp_config, smtp_configured
from config import Config

logger = logging.getLogger(__name__)

# Network timeout (seconds) for the SMTP conversation, so a slow or unreachable
# mail server can never hang the voicemail callback.
_SMTP_TIMEOUT = 15


def message_admin_url(message_id):
    """Return the admin deep link for a saved message."""
    return f"{Config.BASE_URL}/admin/messages/{message_id}"


def _sanitize_header(value):
    """Strip CR/LF and control characters so headers cannot be injected."""
    return "".join(ch for ch in str(value or "") if ch >= " " and ch != "\x7f").strip()


def format_email_subject(caller_id, duration, box_name=None):
    """Build the subject line for a new-voicemail alert."""
    caller = caller_id or "unknown"
    recipient = f" for {box_name}" if box_name else ""
    return _sanitize_header(f"New voicemail{recipient} from {caller} ({duration}s)")


def format_email_body(caller_id, duration, message_id, box_name=None):
    """Build the plain-text body for a new-voicemail alert."""
    caller = caller_id or "unknown"
    lines = [
        f"A new voicemail was saved{f' for {box_name}' if box_name else ''}.",
        "",
        f"From: {caller}",
        f"Duration: {duration}s",
        "",
        f"Listen: {message_admin_url(message_id)}",
    ]
    return "\n".join(lines)


def _default_smtp_factory():
    """Open and authenticate an SMTP connection from the stored settings."""
    config = get_smtp_config()
    if config["port"] == 587:
        server = smtplib.SMTP(config["host"], config["port"], timeout=_SMTP_TIMEOUT)
        server.starttls()
    else:
        server = smtplib.SMTP_SSL(config["host"], config["port"], timeout=_SMTP_TIMEOUT)
    server.login(config["user"], config["password"])
    return server


def _send_email(to, subject, body, smtp_factory=None):
    """Send a single email. Returns a per-recipient result dict."""
    smtp_factory = smtp_factory or _default_smtp_factory
    from_email = get_smtp_config()["from_email"]
    try:
        message = EmailMessage()
        message["Subject"] = _sanitize_header(subject)
        message["From"] = _sanitize_header(from_email)
        message["To"] = _sanitize_header(to)
        message.set_content(body)

        server = smtp_factory()
        try:
            server.send_message(message)
        finally:
            try:
                server.quit()
            except Exception:  # noqa: BLE001 - closing errors are not fatal
                pass
        logger.info("Sent email notification to %s", mask_email(to))
        return {"to": to, "status": "sent", "detail": None}
    except Exception as exc:  # noqa: BLE001 - surface any SMTP/client error
        logger.warning(
            "Could not send email notification to %s", mask_email(to), exc_info=True
        )
        return {"to": to, "status": "failed", "detail": str(exc)}


def _send_to(recipients, subject, body, smtp_factory=None):
    if not recipients:
        return []
    return [
        _send_email(to, subject, body, smtp_factory=smtp_factory) for to in recipients
    ]


def notify_new_message(
    *, message_id, caller_id, duration, created_at=None, box=None, smtp_factory=None
):
    """Send a new-voicemail email to the box's recipients.

    The Family box notifies every admin contact; any other box notifies the
    single contact linked to it. Best-effort: returns per-recipient results and
    never raises. An empty list means nothing was sent (no SMTP config or no
    recipients).
    """
    if not smtp_configured():
        logger.info("Email notifications are not configured; skipping alert.")
        return []

    recipients = resolve_email_recipients(box)
    box_name = box["display_name"] if box else None
    subject = format_email_subject(caller_id, duration, box_name=box_name)
    body = format_email_body(caller_id, duration, message_id, box_name=box_name)
    return _send_to(recipients, subject, body, smtp_factory=smtp_factory)


def send_test_notification(smtp_factory=None):
    """Send a test email to every configured recipient, using a synthetic body."""
    if not smtp_configured():
        return []
    subject = "Test alert from your family call center"
    body = (
        "This is a test from your family call center.\n\n"
        f"Email notifications are working. {Config.BASE_URL}/admin"
    )
    return _send_to(
        get_all_notification_emails(), subject, body, smtp_factory=smtp_factory
    )


def notification_summary():
    """Return notification status for the admin UI.

    Emails are masked so full addresses never appear in rendered HTML.
    """
    recipients = get_all_notification_emails()
    configured = smtp_configured()
    return {
        "enabled": configured and bool(recipients),
        "smtp_configured": configured,
        "recipient_count": len(recipients),
        "masked_recipients": [mask_email(email) for email in recipients],
    }
