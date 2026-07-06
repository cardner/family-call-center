def test_invalid_signature_rejected(client):
    resp = client.post(
        "/call",
        data={"From": "+15551234567"},
        headers={"X-Twilio-Signature": "not-a-valid-signature"},
    )
    assert resp.status_code == 403


def test_valid_signature_accepted(client, twilio_post):
    resp = twilio_post(client, "/call", {"CallSid": "CA" + "0" * 32})
    assert resp.status_code == 200
    assert b"<Response>" in resp.data
