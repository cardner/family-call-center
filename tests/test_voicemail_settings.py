from app.utils.boxes import get_box_by_slug, update_box
from app.utils.db import upsert_contact
from app.utils.settings import set_setting


def test_max_recording_seconds_reflected_in_twiml(client, twilio_post):
    set_setting("max_recording_seconds", "123")
    resp = twilio_post(client, "/voicemail", {})
    assert resp.status_code == 200
    assert b'maxLength="123"' in resp.data


def test_out_of_range_max_seconds_clamped_in_twiml(client, twilio_post):
    # Values outside [10, 600] are clamped when read for TwiML.
    set_setting("max_recording_seconds", "99999")
    resp = twilio_post(client, "/voicemail", {})
    assert resp.status_code == 200
    assert b'maxLength="600"' in resp.data


def test_transcription_setting_caps_max_length_at_120(client, twilio_post):
    set_setting("max_recording_seconds", "300")
    set_setting("transcription_enabled", "true")
    resp = twilio_post(client, "/voicemail", {})
    assert resp.status_code == 200
    assert b'maxLength="120"' in resp.data
    assert b'transcribe="true"' in resp.data


def test_vip_voicemail_personalized(client, twilio_post):
    # A VIP contact hears a personalized voicemail prompt on the chosen box.
    upsert_contact("+15551112222", "Mom", is_vip=True)
    set_setting("personalized_greeting_enabled", "true")
    resp = twilio_post(client, "/voicemail", {"From": "+15551112222"})
    assert resp.status_code == 200
    assert b"Thanks for calling Mom" in resp.data


def test_box_prompt_overrides_global_in_twiml(client, twilio_post):
    # A box with its own prompt uses it instead of the global default.
    fam = get_box_by_slug("family")
    update_box(fam["id"], voicemail_prompt="Family mailbox, leave a note.")
    resp = twilio_post(client, "/voicemail?box=family", {})
    assert resp.status_code == 200
    assert b"Family mailbox, leave a note." in resp.data


def test_box_thanks_used_on_done(client, twilio_post):
    fam = get_box_by_slug("family")
    update_box(fam["id"], voicemail_thanks="Thanks from the family box.")
    resp = twilio_post(client, "/voicemail/done?box=family", {})
    assert resp.status_code == 200
    assert b"Thanks from the family box." in resp.data


def test_voicemail_personalized_for_menu_caller(client, twilio_post):
    upsert_contact("+15551112222", "Mom")
    set_setting("personalized_greeting_enabled", "true")
    set_setting("voicemail_prompt", "Hey {name}, leave a message.")
    resp = twilio_post(client, "/voicemail", {"From": "+15551112222"})
    assert resp.status_code == 200
    assert b"Hey Mom, leave a message." in resp.data


def test_voicemail_not_personalized_when_disabled(client, twilio_post):
    upsert_contact("+15551112222", "Mom")
    resp = twilio_post(client, "/voicemail", {"From": "+15551112222"})
    assert resp.status_code == 200
    assert b"Mom" not in resp.data
