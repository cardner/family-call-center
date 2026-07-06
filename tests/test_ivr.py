def test_call_returns_gather(client, twilio_post):
    resp = twilio_post(client, "/call", {"CallSid": "CA" + "0" * 32})
    assert resp.status_code == 200
    assert b"<Gather" in resp.data


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
