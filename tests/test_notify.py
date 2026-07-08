import app.utils.notify as notify
from app.utils.settings import (
    get_notify_phone_numbers,
    is_valid_e164,
    parse_phone_numbers,
    set_setting,
)


class _FakeMessages:
    def __init__(self, fail=False):
        self.fail = fail
        self.sent = []

    def create(self, body=None, from_=None, to=None):
        if self.fail:
            raise RuntimeError("twilio error")
        self.sent.append({"body": body, "from_": from_, "to": to})
        return object()


class _FakeClient:
    def __init__(self, fail=False):
        self.messages = _FakeMessages(fail=fail)


def test_parse_phone_numbers_splits_and_dedupes():
    raw = "+15551234567, +15559876543\n+15551234567\n\n  "
    assert parse_phone_numbers(raw) == ["+15551234567", "+15559876543"]


def test_is_valid_e164():
    assert is_valid_e164("+15551234567")
    assert not is_valid_e164("5551234567")
    assert not is_valid_e164("+0123")
    assert not is_valid_e164("")


def test_get_notify_phone_numbers_skips_invalid(app):
    set_setting("notify_phone_numbers", "+15551234567,not-a-number,+15559876543")
    assert get_notify_phone_numbers() == ["+15551234567", "+15559876543"]


def test_format_sms_body_includes_link():
    body = notify.format_sms_body("+15551234567", 42, 123)
    assert "+15551234567" in body
    assert "42s" in body
    assert "/admin/messages/123" in body


def test_format_sms_body_includes_box_name():
    body = notify.format_sms_body("+15551234567", 42, 123, box_name="Cody")
    assert "for Cody" in body


def test_mask_phone_keeps_last_four():
    assert notify.mask_phone("+15551234567") == "…4567"


def test_notify_new_message_sends_to_all(app):
    set_setting("notify_phone_numbers", "+15551234567,+15559876543")
    fake = _FakeClient()
    results = notify.notify_new_message(
        message_id=7,
        caller_id="+15550000000",
        duration=10,
        client_factory=lambda: fake,
    )
    assert [r["status"] for r in results] == ["sent", "sent"]
    assert len(fake.messages.sent) == 2
    assert fake.messages.sent[0]["to"] == "+15551234567"


def test_notify_new_message_no_recipients_is_noop(app):
    set_setting("notify_phone_numbers", "")
    results = notify.notify_new_message(
        message_id=1, caller_id="+15550000000", duration=5, client_factory=_FakeClient
    )
    assert results == []


def test_notify_new_message_partial_failure(app):
    set_setting("notify_phone_numbers", "+15551234567")
    results = notify.notify_new_message(
        message_id=1,
        caller_id="+15550000000",
        duration=5,
        client_factory=lambda: _FakeClient(fail=True),
    )
    assert results[0]["status"] == "failed"
    assert results[0]["detail"]


def test_notification_summary_masks(app):
    set_setting("notify_phone_numbers", "+15551234567,+15559876543")
    summary = notify.notification_summary()
    assert summary["enabled"] is True
    assert summary["recipient_count"] == 2
    assert summary["masked_recipients"] == ["…4567", "…6543"]


def test_notification_summary_disabled(app):
    set_setting("notify_phone_numbers", "")
    summary = notify.notification_summary()
    assert summary["enabled"] is False
    assert summary["recipient_count"] == 0


def test_send_test_notification(app):
    set_setting("notify_phone_numbers", "+15551234567")
    fake = _FakeClient()
    results = notify.send_test_notification(client_factory=lambda: fake)
    assert results[0]["status"] == "sent"
    assert len(fake.messages.sent) == 1


def test_notify_new_message_uses_box_recipients(app):
    from app.utils.boxes import get_box_by_slug, update_box

    set_setting("notify_phone_numbers", "+15550000000")
    cody = get_box_by_slug("cody")
    update_box(cody["id"], notify_phone_numbers="+15551112222")
    fake = _FakeClient()
    results = notify.notify_new_message(
        message_id=1,
        caller_id="+15559998888",
        duration=8,
        box=get_box_by_slug("cody"),
        client_factory=lambda: fake,
    )
    assert [r["status"] for r in results] == ["sent"]
    # The box's own recipient is used, not the global list.
    assert fake.messages.sent[0]["to"] == "+15551112222"
    assert "for Cody" in fake.messages.sent[0]["body"]


def test_notify_new_message_box_falls_back_to_global(app):
    from app.utils.boxes import get_box_by_slug

    set_setting("notify_phone_numbers", "+15550000000")
    fake = _FakeClient()
    # A box with no recipients of its own inherits the global list.
    notify.notify_new_message(
        message_id=1,
        caller_id="+15559998888",
        duration=8,
        box=get_box_by_slug("ryan"),
        client_factory=lambda: fake,
    )
    assert fake.messages.sent[0]["to"] == "+15550000000"
