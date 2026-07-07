import app.routes.voicemail as vm
from app.utils.db import get_recording_by_twilio_sid
from app.utils.settings import set_setting


class _FakeResponse:
    content = b"RIFFfake-audio-bytes"

    def raise_for_status(self):
        return None


def _enable_transcription():
    set_setting("transcription_enabled", "true")


def _recording_data(sid, **overrides):
    data = {
        "RecordingSid": sid,
        "RecordingUrl": "https://api.twilio.com/2010-04-01/Recordings/" + sid,
        "RecordingDuration": "8",
        "From": "+15551234567",
    }
    data.update(overrides)
    return data


def test_twiml_includes_transcribe_when_enabled(client, twilio_post):
    _enable_transcription()
    resp = twilio_post(client, "/voicemail", {"From": "+15551234567"})
    assert resp.status_code == 200
    assert b'transcribe="true"' in resp.data
    assert b"/voicemail/transcribe" in resp.data


def test_twiml_omits_transcribe_when_disabled(client, twilio_post):
    resp = twilio_post(client, "/voicemail", {"From": "+15551234567"})
    assert resp.status_code == 200
    assert b'transcribe="true"' not in resp.data


def test_twiml_clamps_max_length_to_120_when_transcribing(client, twilio_post):
    _enable_transcription()
    set_setting("max_recording_seconds", "600")
    resp = twilio_post(client, "/voicemail", {})
    assert b'maxLength="120"' in resp.data


def test_recording_callback_keeps_recording_when_transcribing(
    client, twilio_post, monkeypatch
):
    _enable_transcription()
    monkeypatch.setattr(vm.http_requests, "get", lambda *a, **k: _FakeResponse())
    monkeypatch.setattr(vm, "notify_new_message", lambda **kwargs: [])
    deleted = []
    monkeypatch.setattr(vm, "_delete_from_twilio", lambda sid: deleted.append(sid))

    sid = "RE" + "d" * 32
    resp = twilio_post(client, "/voicemail/callback", _recording_data(sid))

    assert resp.status_code == 204
    # Recording must survive so Twilio can transcribe it.
    assert deleted == []
    row = get_recording_by_twilio_sid(sid)
    assert row["transcript_status"] == "pending"


def test_transcribe_callback_stores_text_and_deletes(
    client, twilio_post, monkeypatch, sample_recording
):
    deleted = []
    monkeypatch.setattr(vm, "_delete_from_twilio", lambda sid: deleted.append(sid))

    sid = "RE" + "e" * 32
    sample_recording(twilio_sid=sid, transcript_status="pending", name="pending.wav")

    data = {
        "RecordingSid": sid,
        "TranscriptionStatus": "completed",
        "TranscriptionText": "Hi it is Mom, please call me back.",
    }
    resp = twilio_post(client, "/voicemail/transcribe", data)

    assert resp.status_code == 204
    assert deleted == [sid]
    row = get_recording_by_twilio_sid(sid)
    assert row["transcript_status"] == "complete"
    assert "Mom" in row["transcript"]


def test_transcribe_callback_marks_failed(
    client, twilio_post, monkeypatch, sample_recording
):
    monkeypatch.setattr(vm, "_delete_from_twilio", lambda sid: None)

    sid = "RE" + "f" * 32
    sample_recording(twilio_sid=sid, transcript_status="pending", name="fail.wav")

    data = {
        "RecordingSid": sid,
        "TranscriptionStatus": "failed",
        "TranscriptionText": "",
    }
    resp = twilio_post(client, "/voicemail/transcribe", data)

    assert resp.status_code == 204
    row = get_recording_by_twilio_sid(sid)
    assert row["transcript_status"] == "failed"


def test_transcribe_callback_deletes_even_when_row_missing(
    client, twilio_post, monkeypatch
):
    deleted = []
    monkeypatch.setattr(vm, "_delete_from_twilio", lambda sid: deleted.append(sid))

    sid = "RE" + "0" * 32
    data = {
        "RecordingSid": sid,
        "TranscriptionStatus": "completed",
        "TranscriptionText": "orphan transcript",
    }
    resp = twilio_post(client, "/voicemail/transcribe", data)

    assert resp.status_code == 204
    assert deleted == [sid]


def test_transcribe_callback_rejects_bad_sid(client, twilio_post):
    resp = twilio_post(
        client,
        "/voicemail/transcribe",
        {"RecordingSid": "not-a-sid", "TranscriptionStatus": "completed"},
    )
    assert resp.status_code == 400
