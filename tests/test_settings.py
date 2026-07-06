from app.utils.settings import (
    DEFAULT_SETTINGS,
    get_all_settings,
    get_setting,
    set_setting,
)
from app.utils.twiml import main_menu_twiml
from tests.helpers import valid_settings


def test_defaults_seeded(app):
    settings = get_all_settings()
    assert settings["greeting"] == DEFAULT_SETTINGS["greeting"]
    assert settings["max_recording_seconds"] == DEFAULT_SETTINGS["max_recording_seconds"]


def test_set_setting_persists(app):
    set_setting("greeting", "Brand new greeting")
    assert get_setting("greeting") == "Brand new greeting"


def test_settings_post_updates_twiml(auth_client):
    data = valid_settings(greeting="Fresh custom greeting here")
    resp = auth_client.post("/admin/settings", data=data, follow_redirects=True)
    assert resp.status_code == 200

    with auth_client.application.test_request_context():
        twiml = main_menu_twiml().get_data(as_text=True)
    assert "Fresh custom greeting here" in twiml
