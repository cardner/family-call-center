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
