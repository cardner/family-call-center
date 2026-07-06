import app.routes.voicemail as vm
from app.utils.db import count_recordings, list_recordings


class _FakeResponse:
    content = b"RIFFfake-audio-bytes"

    def raise_for_status(self):
        return None


def test_callback_saves_file_and_row(client, twilio_post, monkeypatch):
    monkeypatch.setattr(vm.http_requests, "get", lambda *a, **k: _FakeResponse())
    monkeypatch.setattr(vm, "_delete_from_twilio", lambda sid: None)

    sid = "RE" + "a" * 32
    data = {
        "RecordingSid": sid,
        "RecordingUrl": "https://api.twilio.com/2010-04-01/Recordings/" + sid,
        "RecordingDuration": "7",
        "From": "+15551234567",
    }
    resp = twilio_post(client, "/voicemail/callback", data)

    assert resp.status_code == 204
    assert count_recordings() == 1
    row = list_recordings(limit=1)[0]
    assert row["twilio_sid"] == sid
    assert row["duration"] == 7
    assert row["caller_id"] == "+15551234567"
