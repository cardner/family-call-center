import os

from app.utils.db import get_recording


def test_list_shows_seeded_recording(auth_client, sample_recording):
    sample_recording(caller_id="+15559998888")
    resp = auth_client.get("/admin/messages")
    assert resp.status_code == 200
    assert b"+15559998888" in resp.data


def test_detail_page_renders(auth_client, sample_recording):
    rec = sample_recording()
    resp = auth_client.get(f"/admin/messages/{rec['id']}")
    assert resp.status_code == 200


def test_transcript_shown_in_list(auth_client, sample_recording):
    sample_recording(
        caller_id="+15551112222",
        transcript="please call the doctor",
        transcript_status="complete",
    )
    resp = auth_client.get("/admin/messages")
    assert b"please call the doctor" in resp.data


def test_transcript_shown_in_detail(auth_client, sample_recording):
    rec = sample_recording(
        transcript="hello world transcript",
        transcript_status="complete",
    )
    resp = auth_client.get(f"/admin/messages/{rec['id']}")
    assert b"hello world transcript" in resp.data


def test_search_by_transcript(auth_client, sample_recording):
    sample_recording(
        caller_id="+15551112222",
        name="a.wav",
        transcript="pickup groceries",
        transcript_status="complete",
    )
    sample_recording(
        caller_id="+15553334444",
        name="b.wav",
        transcript="dentist appointment",
        transcript_status="complete",
    )
    resp = auth_client.get("/admin/messages?q=groceries")
    assert b"+15551112222" in resp.data
    assert b"+15553334444" not in resp.data


def test_audio_returns_wav(auth_client, sample_recording):
    rec = sample_recording()
    resp = auth_client.get(f"/admin/messages/{rec['id']}/audio")
    assert resp.status_code == 200
    assert resp.mimetype == "audio/wav"


def test_delete_removes_row_and_file(auth_client, sample_recording):
    rec = sample_recording()
    assert os.path.exists(rec["abs_path"])

    resp = auth_client.post(f"/admin/messages/{rec['id']}/delete")
    assert resp.status_code == 302
    assert get_recording(rec["id"]) is None
    assert not os.path.exists(rec["abs_path"])
