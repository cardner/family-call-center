import app.utils.notify as notify
from app.utils.boxes import get_box_by_slug
from app.utils.db import upsert_contact
from app.utils.settings import set_smtp_setting


class _FakeSMTP:
    """Minimal stand-in for a connected smtplib server."""

    def __init__(self, store, fail=False):
        self._store = store
        self._fail = fail

    def send_message(self, message):
        if self._fail:
            raise RuntimeError("smtp error")
        self._store.append(message)

    def quit(self):
        pass


def _factory(store, fail=False):
    return lambda: _FakeSMTP(store, fail=fail)


def _configure_smtp():
    set_smtp_setting("smtp_host", "smtp.fastmail.com")
    set_smtp_setting("smtp_port", "465")
    set_smtp_setting("smtp_user", "box@example.com")
    set_smtp_setting("smtp_password", "app-password")
    set_smtp_setting("smtp_from", "box@example.com")


def test_format_email_body_includes_link():
    body = notify.format_email_body("+15551234567", 42, 123)
    assert "+15551234567" in body
    assert "42s" in body
    assert "/admin/messages/123" in body


def test_format_email_subject_includes_box_name():
    subject = notify.format_email_subject("+15551234567", 42, box_name="Cody")
    assert "for Cody" in subject
    assert "+15551234567" in subject


def test_notify_new_message_family_goes_to_admins(app):
    _configure_smtp()
    upsert_contact("+15550000001", "Ryan", is_admin=True, email="ryan@example.com")
    upsert_contact("+15550000002", "Parent", is_admin=True, email="parent@example.com")
    upsert_contact("+15550000003", "Nobody", email="")

    store = []
    results = notify.notify_new_message(
        message_id=7,
        caller_id="+15559998888",
        duration=10,
        box=get_box_by_slug("family"),
        smtp_factory=_factory(store),
    )
    assert [r["status"] for r in results] == ["sent", "sent"]
    recipients = {m["To"] for m in store}
    assert recipients == {"ryan@example.com", "parent@example.com"}


def test_notify_new_message_personal_box_goes_to_owner(app):
    _configure_smtp()
    cody = get_box_by_slug("cody")
    upsert_contact("+15550000009", "Ryan", is_admin=True, email="ryan@example.com")
    upsert_contact("+15550000010", "Cody", email="cody@example.com", box_id=cody["id"])

    store = []
    results = notify.notify_new_message(
        message_id=1,
        caller_id="+15559998888",
        duration=8,
        box=cody,
        smtp_factory=_factory(store),
    )
    assert [r["status"] for r in results] == ["sent"]
    assert store[0]["To"] == "cody@example.com"
    assert "for Cody" in store[0]["Subject"]


def test_notify_new_message_child_box_also_emails_parents(app):
    _configure_smtp()
    cody = get_box_by_slug("cody")
    upsert_contact("+15550000009", "Ryan", is_parent=True, email="ryan@example.com")
    upsert_contact(
        "+15550000010",
        "Cody",
        email="cody@example.com",
        box_id=cody["id"],
        is_child=True,
    )

    store = []
    results = notify.notify_new_message(
        message_id=1,
        caller_id="+15559998888",
        duration=8,
        box=cody,
        smtp_factory=_factory(store),
    )
    assert [r["status"] for r in results] == ["sent", "sent"]
    assert {m["To"] for m in store} == {"cody@example.com", "ryan@example.com"}


def test_notify_new_message_noop_when_smtp_unconfigured(app):
    upsert_contact("+15550000001", "Ryan", is_admin=True, email="ryan@example.com")
    store = []
    results = notify.notify_new_message(
        message_id=1,
        caller_id="+15559998888",
        duration=5,
        box=get_box_by_slug("family"),
        smtp_factory=_factory(store),
    )
    assert results == []
    assert store == []


def test_notify_new_message_no_recipients_is_noop(app):
    _configure_smtp()
    store = []
    results = notify.notify_new_message(
        message_id=1,
        caller_id="+15559998888",
        duration=5,
        box=get_box_by_slug("family"),
        smtp_factory=_factory(store),
    )
    assert results == []
    assert store == []


def test_notify_new_message_partial_failure(app):
    _configure_smtp()
    upsert_contact("+15550000001", "Ryan", is_admin=True, email="ryan@example.com")
    results = notify.notify_new_message(
        message_id=1,
        caller_id="+15559998888",
        duration=5,
        box=get_box_by_slug("family"),
        smtp_factory=_factory([], fail=True),
    )
    assert results[0]["status"] == "failed"
    assert results[0]["detail"]


def test_notify_header_injection_stripped(app):
    _configure_smtp()
    upsert_contact("+15550000001", "Ryan", is_admin=True, email="ryan@example.com")
    store = []
    notify.notify_new_message(
        message_id=1,
        caller_id="+15559998888\r\nBcc: attacker@evil.com",
        duration=5,
        box=get_box_by_slug("family"),
        smtp_factory=_factory(store),
    )
    # Exactly one recipient and no CR/LF survives, so the caller ID cannot
    # inject an extra header (the inline text is harmless without a newline).
    assert len(store) == 1
    assert store[0]["To"] == "ryan@example.com"
    subject = str(store[0]["Subject"])
    assert "\r" not in subject and "\n" not in subject


def test_send_test_notification_dedups(app):
    _configure_smtp()
    cody = get_box_by_slug("cody")
    # Cody is both an admin and a box owner; he should receive a single email.
    upsert_contact(
        "+15550000010",
        "Cody",
        is_admin=True,
        email="cody@example.com",
        box_id=cody["id"],
    )
    upsert_contact("+15550000002", "Parent", is_admin=True, email="parent@example.com")

    store = []
    results = notify.send_test_notification(smtp_factory=_factory(store))
    assert all(r["status"] == "sent" for r in results)
    recipients = sorted(m["To"] for m in store)
    assert recipients == ["cody@example.com", "parent@example.com"]


def test_send_test_notification_noop_when_unconfigured(app):
    upsert_contact("+15550000001", "Ryan", is_admin=True, email="ryan@example.com")
    assert notify.send_test_notification(smtp_factory=_factory([])) == []


def test_notification_summary_masks(app):
    _configure_smtp()
    upsert_contact("+15550000001", "Ryan", is_admin=True, email="ryan@example.com")
    summary = notify.notification_summary()
    assert summary["enabled"] is True
    assert summary["smtp_configured"] is True
    assert summary["recipient_count"] == 1
    assert summary["masked_recipients"] == ["r…@example.com"]


def test_notification_summary_disabled_without_smtp(app):
    upsert_contact("+15550000001", "Ryan", is_admin=True, email="ryan@example.com")
    summary = notify.notification_summary()
    assert summary["enabled"] is False
    assert summary["smtp_configured"] is False
