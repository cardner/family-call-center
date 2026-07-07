from app.utils.settings import DEFAULT_SETTINGS, get_max_recording_seconds, get_setting
from app.utils.twiml import main_menu_twiml
from tests.helpers import valid_settings


def test_greeting_over_max_length_rejected(auth_client):
    resp = auth_client.post(
        "/admin/settings", data=valid_settings(greeting="x" * 501)
    )
    assert resp.status_code == 200  # re-rendered with errors, not saved
    assert get_setting("greeting") == DEFAULT_SETTINGS["greeting"]


def test_max_recording_seconds_out_of_range_rejected(auth_client):
    resp = auth_client.post(
        "/admin/settings", data=valid_settings(max_recording_seconds="9999")
    )
    assert resp.status_code == 200
    assert get_setting("max_recording_seconds") == DEFAULT_SETTINGS[
        "max_recording_seconds"
    ]
    assert get_max_recording_seconds() == 300


def test_script_in_greeting_is_stripped_and_twiml_safe(auth_client):
    auth_client.post(
        "/admin/settings",
        data=valid_settings(greeting="<script>alert(1)</script>Hello"),
        follow_redirects=True,
    )
    stored = get_setting("greeting")
    assert "<script" not in stored.lower()
    assert "Hello" in stored

    with auth_client.application.test_request_context():
        twiml = main_menu_twiml().get_data(as_text=True)
    assert "<script" not in twiml.lower()


def test_ssml_greeting_renders_break_and_emphasis_in_twiml(auth_client):
    greeting = (
        'Hi. <break time="300ms"/> '
        '<emphasis level="moderate">press 1</emphasis>.'
    )
    auth_client.post(
        "/admin/settings",
        data=valid_settings(greeting=greeting),
        follow_redirects=True,
    )
    assert get_setting("greeting") == greeting

    with auth_client.application.test_request_context():
        twiml = main_menu_twiml().get_data(as_text=True)
    assert '<break time="300ms"' in twiml
    assert '<emphasis level="moderate">press 1</emphasis>' in twiml
    assert "&lt;break" not in twiml


def test_login_open_redirect_blocked(client):
    resp = client.post(
        "/admin/login?next=https://evil.com",
        data={"username": "admin", "password": "s3cret-pass"},
    )
    assert resp.status_code == 302
    assert "evil.com" not in resp.headers["Location"]


def test_callback_non_twilio_url_rejected(client, twilio_post):
    sid = "RE" + "a" * 32
    data = {
        "RecordingSid": sid,
        "RecordingUrl": "https://evil.example.com/steal",
        "RecordingDuration": "5",
        "From": "+15551234567",
    }
    resp = twilio_post(client, "/voicemail/callback", data)
    assert resp.status_code == 400


def test_callback_bad_recording_sid_rejected(client, twilio_post):
    data = {
        "RecordingSid": "not-a-sid",
        "RecordingUrl": "https://api.twilio.com/x",
        "RecordingDuration": "5",
        "From": "+15551234567",
    }
    resp = twilio_post(client, "/voicemail/callback", data)
    assert resp.status_code == 400


def test_pagination_negative_page_clamped(auth_client, sample_recording):
    sample_recording()
    resp = auth_client.get("/admin/messages?page=-1")
    assert resp.status_code == 200
