import app.routes.admin as admin_mod
from app.utils.blocklist_import import SEED_SOURCE
from app.utils.db import (
    count_blocked,
    count_blocked_by_source,
    get_blocked_by_phone,
    upsert_blocked,
)


def test_blocked_list_page_renders(auth_client):
    upsert_blocked("+15559998888", note="robocaller")
    resp = auth_client.get("/admin/blocked")
    assert resp.status_code == 200
    assert b"+15559998888" in resp.data
    assert b"robocaller" in resp.data


def test_manual_add_normalizes_and_stores(auth_client):
    resp = auth_client.post(
        "/admin/blocked/new",
        data={"phone": "5559998888", "note": "wrong number"},
    )
    assert resp.status_code == 302
    row = get_blocked_by_phone("+15559998888")
    assert row is not None
    assert row["note"] == "wrong number"
    assert row["source"] == "user"


def test_manual_add_rejects_bad_phone(auth_client):
    resp = auth_client.post(
        "/admin/blocked/new",
        data={"phone": "nope", "note": ""},
    )
    assert resp.status_code == 200  # re-renders form with error
    assert count_blocked() == 0


def test_edit_note(auth_client):
    upsert_blocked("+15559998888", note="old")
    row = get_blocked_by_phone("+15559998888")
    resp = auth_client.post(
        f"/admin/blocked/{row['id']}/edit",
        data={"phone": "+15559998888", "note": "new note"},
    )
    assert resp.status_code == 302
    assert get_blocked_by_phone("+15559998888")["note"] == "new note"


def test_delete_removes_row(auth_client):
    upsert_blocked("+15559998888")
    row = get_blocked_by_phone("+15559998888")
    resp = auth_client.post(f"/admin/blocked/{row['id']}/delete")
    assert resp.status_code == 302
    assert count_blocked() == 0


def test_block_from_message(auth_client, sample_recording):
    rec = sample_recording(caller_id="+15551234567")
    resp = auth_client.post(f"/admin/messages/{rec['id']}/block")
    assert resp.status_code == 302
    row = get_blocked_by_phone("+15551234567")
    assert row is not None
    assert row["source"] == "user"
    assert f"message #{rec['id']}" in row["note"]


def test_block_from_message_unknown_caller(auth_client, sample_recording):
    rec = sample_recording(caller_id="unknown")
    resp = auth_client.post(f"/admin/messages/{rec['id']}/block")
    assert resp.status_code == 302
    assert count_blocked() == 0


def test_message_detail_shows_block_button(auth_client, sample_recording):
    rec = sample_recording(caller_id="+15551234567")
    resp = auth_client.get(f"/admin/messages/{rec['id']}")
    assert b"Block this caller" in resp.data


def test_message_detail_hides_block_button_when_blocked(auth_client, sample_recording):
    upsert_blocked("+15551234567")
    rec = sample_recording(caller_id="+15551234567")
    resp = auth_client.get(f"/admin/messages/{rec['id']}")
    assert b"Block this caller" not in resp.data
    assert b"Caller blocked" in resp.data


def test_import_starter_via_admin(auth_client, monkeypatch):
    sample = [
        {"number": "+13042635785", "type": "robocall", "reports": 453, "description": "x"},
        {"number": "+15551234567", "type": "scam", "reports": 10, "description": "y"},
    ]
    monkeypatch.setattr(
        admin_mod, "import_callshield_seed", lambda: {"added": 2, "matched": 2, "skipped": 0}
    )
    resp = auth_client.post("/admin/blocked/import-starter")
    assert resp.status_code == 302


def test_remove_imported_keeps_user_blocks(auth_client):
    upsert_blocked("+15551112222", note="manual", source="user")
    upsert_blocked("+13042635785", note="seed", source=SEED_SOURCE)
    resp = auth_client.post("/admin/blocked/remove-imported")
    assert resp.status_code == 302
    assert count_blocked_by_source(SEED_SOURCE) == 0
    assert get_blocked_by_phone("+15551112222") is not None
