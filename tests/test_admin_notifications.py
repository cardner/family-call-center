import app.routes.admin as admin_mod
from app.utils.settings import get_setting
from tests.helpers import valid_settings


def test_settings_saves_recipients(auth_client):
    data = valid_settings(notify_phone_numbers="+15551234567\n+15559876543")
    resp = auth_client.post("/admin/settings", data=data, follow_redirects=True)
    assert resp.status_code == 200
    assert get_setting("notify_phone_numbers") == "+15551234567,+15559876543"


def test_settings_rejects_invalid_recipient(auth_client):
    data = valid_settings(notify_phone_numbers="not-a-number")
    resp = auth_client.post("/admin/settings", data=data)
    assert resp.status_code == 200
    assert b"Invalid phone number" in resp.data
    assert get_setting("notify_phone_numbers") == ""


def test_settings_get_prefills_recipients(auth_client):
    admin_mod.set_setting("notify_phone_numbers", "+15551234567,+15559876543")
    resp = auth_client.get("/admin/settings")
    assert resp.status_code == 200
    assert b"+15551234567" in resp.data


def test_connection_shows_off_when_unconfigured(auth_client):
    resp = auth_client.get("/admin/connection")
    assert resp.status_code == 200
    assert b"OFF" in resp.data


def test_connection_shows_on_with_recipients(auth_client):
    admin_mod.set_setting("notify_phone_numbers", "+15551234567")
    resp = auth_client.get("/admin/connection")
    assert resp.status_code == 200
    assert b"ON" in resp.data
    assert b"\xe2\x80\xa64567" in resp.data  # masked "…4567"


def test_notify_test_requires_auth(client):
    resp = client.post("/admin/connection/notify-test")
    assert resp.status_code == 302
    assert "/admin/login" in resp.headers["Location"]


def test_notify_test_requires_csrf(make_app):
    app = make_app(csrf_enabled=True)
    client = app.test_client()
    with client.session_transaction() as sess:
        sess["admin_logged_in"] = True
    resp = client.post("/admin/connection/notify-test")
    assert resp.status_code == 400


def test_notify_test_sends_with_recipients(auth_client, monkeypatch):
    admin_mod.set_setting("notify_phone_numbers", "+15551234567")
    monkeypatch.setattr(
        admin_mod,
        "send_test_notification",
        lambda: [{"to": "+15551234567", "status": "sent", "detail": None}],
    )
    resp = auth_client.post("/admin/connection/notify-test", follow_redirects=True)
    assert resp.status_code == 200
    assert b"Test SMS sent to 1 recipient" in resp.data


def test_notify_test_flashes_when_unconfigured(auth_client):
    resp = auth_client.post("/admin/connection/notify-test", follow_redirects=True)
    assert resp.status_code == 200
    assert b"No SMS recipients configured" in resp.data
