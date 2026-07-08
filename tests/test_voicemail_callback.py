import app.routes.voicemail as vm
from app.utils.boxes import get_box_by_slug
from app.utils.db import count_recordings, list_recordings


class _FakeResponse:
    content = b"RIFFfake-audio-bytes"

    def raise_for_status(self):
        return None


def test_callback_saves_file_and_row(client, twilio_post, monkeypatch):
    monkeypatch.setattr(vm.http_requests, "get", lambda *a, **k: _FakeResponse())
    monkeypatch.setattr(vm, "_delete_from_twilio", lambda sid: None)
    monkeypatch.setattr(vm, "notify_new_message", lambda **kwargs: [])

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


def test_callback_deletes_from_twilio_when_transcription_disabled(
    client, twilio_post, monkeypatch
):
    monkeypatch.setattr(vm.http_requests, "get", lambda *a, **k: _FakeResponse())
    monkeypatch.setattr(vm, "notify_new_message", lambda **kwargs: [])
    deleted = []
    monkeypatch.setattr(vm, "_delete_from_twilio", lambda sid: deleted.append(sid))

    sid = "RE" + "9" * 32
    data = {
        "RecordingSid": sid,
        "RecordingUrl": "https://api.twilio.com/2010-04-01/Recordings/" + sid,
        "RecordingDuration": "5",
        "From": "+15551234567",
    }
    resp = twilio_post(client, "/voicemail/callback", data)

    assert resp.status_code == 204
    # With transcription off (the default), delete immediately.
    assert deleted == [sid]


def test_callback_notifies_after_save(client, twilio_post, monkeypatch):
    monkeypatch.setattr(vm.http_requests, "get", lambda *a, **k: _FakeResponse())
    monkeypatch.setattr(vm, "_delete_from_twilio", lambda sid: None)

    calls = []
    monkeypatch.setattr(vm, "notify_new_message", lambda **kwargs: calls.append(kwargs))

    sid = "RE" + "b" * 32
    data = {
        "RecordingSid": sid,
        "RecordingUrl": "https://api.twilio.com/2010-04-01/Recordings/" + sid,
        "RecordingDuration": "9",
        "From": "+15551234567",
    }
    resp = twilio_post(client, "/voicemail/callback", data)

    assert resp.status_code == 204
    assert len(calls) == 1
    assert calls[0]["caller_id"] == "+15551234567"
    assert calls[0]["duration"] == 9
    assert calls[0]["message_id"] == list_recordings(limit=1)[0]["id"]


def test_callback_does_not_notify_on_invalid_sid(client, twilio_post, monkeypatch):
    calls = []
    monkeypatch.setattr(vm, "notify_new_message", lambda **kwargs: calls.append(kwargs))

    data = {
        "RecordingSid": "not-a-sid",
        "RecordingUrl": "https://api.twilio.com/2010-04-01/Recordings/x",
        "RecordingDuration": "5",
    }
    resp = twilio_post(client, "/voicemail/callback", data)

    assert resp.status_code == 400
    assert calls == []


def test_voicemail_embeds_caller_in_callback_url(client, twilio_post):
    resp = twilio_post(
        client, "/voicemail", {"From": "+15551234567", "CallSid": "CA" + "0" * 32}
    )
    assert resp.status_code == 200
    assert b"caller=%2B15551234567" in resp.data


def test_callback_saves_box_id_and_notifies_box(client, twilio_post, monkeypatch):
    monkeypatch.setattr(vm.http_requests, "get", lambda *a, **k: _FakeResponse())
    monkeypatch.setattr(vm, "_delete_from_twilio", lambda sid: None)
    calls = []
    monkeypatch.setattr(vm, "notify_new_message", lambda **kwargs: calls.append(kwargs))

    sid = "RE" + "d" * 32
    data = {
        "RecordingSid": sid,
        "RecordingUrl": "https://api.twilio.com/2010-04-01/Recordings/" + sid,
        "RecordingDuration": "6",
        "From": "+15551234567",
    }
    resp = twilio_post(client, "/voicemail/callback?box=cody", data)

    assert resp.status_code == 204
    cody = get_box_by_slug("cody")
    row = list_recordings(limit=1)[0]
    assert row["box_id"] == cody["id"]
    assert row["box_name"] == "Cody"
    # The box is handed to the notifier so it can pick the right recipients.
    assert calls[0]["box"]["slug"] == "cody"


def test_callback_uses_caller_query_param(client, twilio_post, monkeypatch):
    monkeypatch.setattr(vm.http_requests, "get", lambda *a, **k: _FakeResponse())
    monkeypatch.setattr(vm, "_delete_from_twilio", lambda sid: None)

    sid = "RE" + "c" * 32
    data = {
        "RecordingSid": sid,
        "RecordingUrl": "https://api.twilio.com/2010-04-01/Recordings/" + sid,
        "RecordingDuration": "4",
    }
    resp = twilio_post(client, "/voicemail/callback?caller=%2B15559998888", data)

    assert resp.status_code == 204
    row = list_recordings(limit=1)[0]
    assert row["caller_id"] == "+15559998888"
