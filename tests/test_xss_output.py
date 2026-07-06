from app.utils.db import log_recording
from app.utils.settings import set_setting


def test_caller_id_html_escaped_in_list(auth_client):
    log_recording(
        created_at="2026-07-05T12:00:00+00:00",
        caller_id="<b>xss</b>",
        duration=3,
        filename="2026/07/05/a.wav",
        file_size=10,
        twilio_sid="RE" + "b" * 32,
    )
    resp = auth_client.get("/admin/messages")
    assert resp.status_code == 200
    assert b"<b>xss</b>" not in resp.data
    assert b"&lt;b&gt;xss&lt;/b&gt;" in resp.data


def test_settings_value_escaped_in_html(auth_client):
    # Stored directly to exercise output escaping (route sanitizes on save).
    set_setting("greeting", "<i>hi</i>")
    resp = auth_client.get("/admin/settings")
    assert resp.status_code == 200
    assert b"<i>hi</i>" not in resp.data
    assert b"&lt;i&gt;hi&lt;/i&gt;" in resp.data
