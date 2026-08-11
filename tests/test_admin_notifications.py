import app.routes.admin as admin_mod
from app.utils.db import upsert_contact
from app.utils.settings import get_smtp_setting, set_smtp_setting
from config import Config
from tests.helpers import valid_settings


def _smtp_payload(**overrides):
    data = valid_settings(
        smtp_host="smtp.fastmail.com",
        smtp_port="465",
        smtp_user="box@example.com",
        smtp_password="app-password",
        smtp_from="",
    )
    data.update(overrides)
    return data


def test_settings_saves_smtp(auth_client):
    resp = auth_client.post("/admin/settings", data=_smtp_payload(), follow_redirects=True)
    assert resp.status_code == 200
    assert get_smtp_setting("smtp_user") == "box@example.com"
    assert get_smtp_setting("smtp_password") == "app-password"


def test_settings_rejects_private_smtp_host(auth_client):
    resp = auth_client.post("/admin/settings", data=_smtp_payload(smtp_host="127.0.0.1"))
    assert resp.status_code == 200
    assert b"valid mail server hostname" in resp.data
    assert get_smtp_setting("smtp_user") == ""


def test_settings_blank_password_keeps_existing(auth_client):
    set_smtp_setting("smtp_password", "original-secret")
    resp = auth_client.post(
        "/admin/settings", data=_smtp_payload(smtp_password=""), follow_redirects=True
    )
    assert resp.status_code == 200
    assert get_smtp_setting("smtp_password") == "original-secret"


def test_settings_get_does_not_prefill_password(auth_client):
    set_smtp_setting("smtp_password", "supersecretvalue")
    resp = auth_client.get("/admin/settings")
    assert resp.status_code == 200
    assert b"supersecretvalue" not in resp.data


def test_settings_smtp_not_saved_without_key(auth_client, monkeypatch):
    monkeypatch.setattr(Config, "SETTINGS_ENCRYPTION_KEY", None)
    resp = auth_client.post("/admin/settings", data=_smtp_payload(), follow_redirects=True)
    assert resp.status_code == 200
    assert b"SETTINGS_ENCRYPTION_KEY is not configured" in resp.data


def test_connection_shows_off_when_unconfigured(auth_client):
    resp = auth_client.get("/admin/connection")
    assert resp.status_code == 200
    assert b"OFF" in resp.data


def test_connection_shows_on_with_recipients(auth_client):
    set_smtp_setting("smtp_host", "smtp.fastmail.com")
    set_smtp_setting("smtp_user", "box@example.com")
    set_smtp_setting("smtp_password", "app-password")
    set_smtp_setting("smtp_from", "box@example.com")
    upsert_contact("+15551234567", "Ryan", is_admin=True, email="ryan@example.com")
    resp = auth_client.get("/admin/connection")
    assert resp.status_code == 200
    assert b"ON" in resp.data
    assert b"@example.com" in resp.data


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
    monkeypatch.setattr(
        admin_mod,
        "send_test_notification",
        lambda: [{"to": "ryan@example.com", "status": "sent", "detail": None}],
    )
    resp = auth_client.post("/admin/connection/notify-test", follow_redirects=True)
    assert resp.status_code == 200
    assert b"Test email sent to 1 recipient" in resp.data


def test_notify_test_flashes_when_unconfigured(auth_client):
    resp = auth_client.post("/admin/connection/notify-test", follow_redirects=True)
    assert resp.status_code == 200
    assert b"No email recipients configured" in resp.data
