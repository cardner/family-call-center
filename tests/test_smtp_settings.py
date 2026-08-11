import pytest

from app.utils.db import get_connection
from app.utils.settings import (
    SMTP_SETTING_KEYS,
    get_smtp_config,
    get_smtp_setting,
    is_valid_smtp_host,
    normalize_smtp_port,
    set_smtp_setting,
    smtp_configured,
)
from app.utils.settings_crypto import (
    SettingsEncryptionError,
    decrypt_setting_value,
    encrypt_setting_value,
    is_encrypted_value,
)
from config import Config


def _raw_setting(key):
    with get_connection() as conn:
        row = conn.execute(
            "SELECT value FROM settings WHERE key = ?", (key,)
        ).fetchone()
    return row["value"] if row else None


def test_encrypt_decrypt_roundtrip():
    token = encrypt_setting_value("hunter2")
    assert is_encrypted_value(token)
    assert token != "hunter2"
    assert decrypt_setting_value(token) == "hunter2"


def test_encrypt_requires_key(monkeypatch):
    monkeypatch.setattr(Config, "SETTINGS_ENCRYPTION_KEY", None)
    with pytest.raises(SettingsEncryptionError):
        encrypt_setting_value("secret")


def test_smtp_values_stored_encrypted(app):
    set_smtp_setting("smtp_password", "app-password")
    raw = _raw_setting("smtp_password")
    assert raw is not None
    assert raw != "app-password"
    assert is_encrypted_value(raw)
    assert get_smtp_setting("smtp_password") == "app-password"


def test_get_smtp_setting_defaults(app):
    assert get_smtp_setting("smtp_host") == "smtp.fastmail.com"
    assert get_smtp_setting("smtp_user") == ""


def test_smtp_configured_requires_all_fields(app):
    assert smtp_configured() is False
    set_smtp_setting("smtp_user", "box@example.com")
    set_smtp_setting("smtp_password", "app-password")
    set_smtp_setting("smtp_from", "box@example.com")
    assert smtp_configured() is True


def test_smtp_configured_false_without_key(app, monkeypatch):
    set_smtp_setting("smtp_user", "box@example.com")
    set_smtp_setting("smtp_password", "app-password")
    set_smtp_setting("smtp_from", "box@example.com")
    monkeypatch.setattr(Config, "SETTINGS_ENCRYPTION_KEY", None)
    assert smtp_configured() is False


def test_get_smtp_config_defaults_from_to_user(app):
    set_smtp_setting("smtp_user", "box@example.com")
    set_smtp_setting("smtp_from", "")
    config = get_smtp_config()
    assert config["from_email"] == "box@example.com"


def test_normalize_smtp_port():
    assert normalize_smtp_port("587") == 587
    assert normalize_smtp_port("465") == 465
    assert normalize_smtp_port("25") == 465
    assert normalize_smtp_port("garbage") == 465


@pytest.mark.parametrize(
    "host",
    ["smtp.fastmail.com", "mail.example.co.uk"],
)
def test_valid_smtp_hosts(host):
    assert is_valid_smtp_host(host)


@pytest.mark.parametrize(
    "host",
    [
        "",
        "localhost",
        "127.0.0.1",
        "10.0.0.5",
        "169.254.169.254",
        "192.168.1.1",
        "smtp.fastmail.com:465",
        "http://smtp.fastmail.com",
        "smtp.fastmail.com/path",
    ],
)
def test_invalid_smtp_hosts(host):
    assert not is_valid_smtp_host(host)


def test_smtp_setting_keys_defined():
    assert set(SMTP_SETTING_KEYS) == {
        "smtp_host",
        "smtp_port",
        "smtp_user",
        "smtp_password",
        "smtp_from",
    }
