def test_audio_requires_auth(client, sample_recording):
    rec = sample_recording()
    resp = client.get(f"/admin/messages/{rec['id']}/audio")
    assert resp.status_code == 302
    assert "/admin/login" in resp.headers["Location"]


def test_missing_recording_audio_404(auth_client):
    resp = auth_client.get("/admin/messages/999999/audio")
    assert resp.status_code == 404


def test_delete_via_get_not_allowed(auth_client, sample_recording):
    rec = sample_recording()
    resp = auth_client.get(f"/admin/messages/{rec['id']}/delete")
    assert resp.status_code == 405


def test_non_numeric_message_id_404(auth_client):
    for bad in ["abc", "-1", "1;DROP"]:
        assert auth_client.get(f"/admin/messages/{bad}").status_code == 404
