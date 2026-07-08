from app.utils.db import upsert_blocked, upsert_contact
from app.utils.settings import set_setting


def test_call_returns_gather(client, twilio_post):
    resp = twilio_post(client, "/call", {"CallSid": "CA" + "0" * 32})
    assert resp.status_code == 200
    assert b"<Gather" in resp.data


def test_blocked_caller_rejected(client, twilio_post):
    upsert_blocked("+15559998888")
    resp = twilio_post(
        client, "/call", {"From": "+15559998888", "CallSid": "CA" + "0" * 32}
    )
    assert resp.status_code == 200
    assert b"<Reject" in resp.data
    assert b"<Gather" not in resp.data


def test_blocked_caller_message_action(client, twilio_post):
    upsert_blocked("+15559998888")
    set_setting("block_action", "message")
    set_setting("blocked_caller_message", "You are blocked. Goodbye.")
    resp = twilio_post(
        client, "/call", {"From": "+15559998888", "CallSid": "CA" + "0" * 32}
    )
    assert resp.status_code == 200
    assert b"<Hangup" in resp.data
    assert b"<Reject" not in resp.data
    assert b"<Gather" not in resp.data


def test_vip_contact_skips_menu(client, twilio_post):
    upsert_contact("+15551112222", "Mom", skip_ivr_menu=True)
    resp = twilio_post(
        client, "/call", {"From": "+15551112222", "CallSid": "CA" + "0" * 32}
    )
    assert resp.status_code == 200
    assert b"/voicemail</Redirect>" in resp.data
    assert b"<Gather" not in resp.data


def test_normal_caller_gets_menu(client, twilio_post):
    upsert_contact("+15551112222", "Mom")
    resp = twilio_post(
        client, "/call", {"From": "+15551112222", "CallSid": "CA" + "0" * 32}
    )
    assert resp.status_code == 200
    assert b"<Gather" in resp.data


def test_allow_beats_block(client, twilio_post):
    # A VIP contact who is also on the blocklist is allowed through to voicemail.
    upsert_blocked("+15551112222")
    upsert_contact("+15551112222", "Mom", skip_ivr_menu=True)
    resp = twilio_post(
        client, "/call", {"From": "+15551112222", "CallSid": "CA" + "0" * 32}
    )
    assert resp.status_code == 200
    assert b"<Reject" not in resp.data
    assert b"/voicemail</Redirect>" in resp.data


def test_route_digit_one_redirects_to_voicemail(client, twilio_post):
    resp = twilio_post(client, "/call/route", {"Digits": "1"})
    assert resp.status_code == 200
    assert b"/voicemail</Redirect>" in resp.data


def test_route_invalid_digit_replays_menu(client, twilio_post):
    resp = twilio_post(client, "/call/route", {"Digits": "9"})
    assert resp.status_code == 200
    assert b"/voicemail</Redirect>" not in resp.data
    assert b"/call</Redirect>" in resp.data


def test_route_multichar_digits_replays_menu(client, twilio_post):
    resp = twilio_post(client, "/call/route", {"Digits": "12"})
    assert resp.status_code == 200
    assert b"/voicemail</Redirect>" not in resp.data
    assert b"/call</Redirect>" in resp.data


def test_personalized_greeting_for_known_contact(client, twilio_post):
    upsert_contact("+15551112222", "Mom")
    set_setting("personalized_greeting_enabled", "true")
    set_setting("greeting", "Hi {name}. Welcome.")
    resp = twilio_post(
        client, "/call", {"From": "+15551112222", "CallSid": "CA" + "0" * 32}
    )
    assert resp.status_code == 200
    assert b"Hi Mom." in resp.data


def test_personalized_greeting_auto_prefix(client, twilio_post):
    upsert_contact("+15551112222", "Mom")
    set_setting("personalized_greeting_enabled", "true")
    resp = twilio_post(
        client, "/call", {"From": "+15551112222", "CallSid": "CA" + "0" * 32}
    )
    assert resp.status_code == 200
    assert b"Hi Mom" in resp.data


def test_personalized_greeting_disabled(client, twilio_post):
    upsert_contact("+15551112222", "Mom")
    set_setting("greeting", "Hi {name}. Welcome.")
    resp = twilio_post(
        client, "/call", {"From": "+15551112222", "CallSid": "CA" + "0" * 32}
    )
    assert resp.status_code == 200
    assert b"Mom" not in resp.data
    assert b"Welcome." in resp.data
