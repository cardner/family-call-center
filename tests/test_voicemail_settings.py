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
