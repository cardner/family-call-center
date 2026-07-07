from app.utils.db import count_unread_recordings


def test_new_recording_is_unread(sample_recording):
    sample_recording()
    assert count_unread_recordings() == 1


def test_opening_detail_marks_read(auth_client, sample_recording):
    rec = sample_recording()
    assert count_unread_recordings() == 1

    resp = auth_client.get(f"/admin/messages/{rec['id']}")
    assert resp.status_code == 200
    assert count_unread_recordings() == 0


def test_mark_all_read_endpoint(auth_client, sample_recording):
    sample_recording(name="a.wav", caller_id="+15550000001")
    sample_recording(name="b.wav", caller_id="+15550000002")
    assert count_unread_recordings() == 2

    resp = auth_client.post("/admin/messages/mark-all-read")
    assert resp.status_code == 302
    assert count_unread_recordings() == 0


def test_inbox_shows_new_badge_for_unread(auth_client, sample_recording):
    sample_recording()
    resp = auth_client.get("/admin/messages")
    assert resp.status_code == 200
    assert b"New" in resp.data


def test_unread_filter_hides_read_messages(auth_client, sample_recording):
    sample_recording(
        name="read.wav",
        caller_id="+15550000001",
        read_at="2026-07-05T13:00:00+00:00",
    )
    sample_recording(name="unread.wav", caller_id="+15550000002")

    resp = auth_client.get("/admin/messages?unread=1")
    assert resp.status_code == 200
    assert b"+15550000002" in resp.data
    assert b"+15550000001" not in resp.data


def test_dashboard_shows_unread_count(auth_client, sample_recording):
    sample_recording()
    resp = auth_client.get("/admin/")
    assert resp.status_code == 200
    assert b"Unread" in resp.data
