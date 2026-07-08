import io

from app.utils.contacts import parse_contacts_csv, resolve_caller_display
from app.utils.db import count_contacts, get_contact_by_phone, upsert_contact
from app.utils.phone import normalize_phone


def test_normalize_phone_us_10_digit():
    assert normalize_phone("555 123 4567") == "+15551234567"
    assert normalize_phone("(555) 123-4567") == "+15551234567"


def test_normalize_phone_11_digit_us():
    assert normalize_phone("15551234567") == "+15551234567"


def test_normalize_phone_e164_passthrough():
    assert normalize_phone("+441234567890") == "+441234567890"


def test_normalize_phone_rejects_junk():
    assert normalize_phone("hello") is None
    assert normalize_phone("") is None
    assert normalize_phone(None) is None


def test_upsert_and_exact_resolution():
    upsert_contact("+15551234567", "Mom")
    display = resolve_caller_display("+15551234567")
    assert display["name"] == "Mom"


def test_resolution_tail_match_without_country_code():
    upsert_contact("+15551234567", "Mom")
    display = resolve_caller_display("5551234567")
    assert display["name"] == "Mom"


def test_resolution_unknown_returns_none():
    display = resolve_caller_display("+19998887777")
    assert display["name"] is None


def test_upsert_updates_existing_name():
    upsert_contact("+15551234567", "Mom")
    upsert_contact("+15551234567", "Mother")
    assert count_contacts() == 1
    assert get_contact_by_phone("+15551234567")["display_name"] == "Mother"


def test_parse_csv_with_header_and_invalid_rows():
    text = (
        "phone,display_name\n"
        "+15551234567,Mom\n"
        "5559876543,Dr. Smith\n"
        "\n"
        "notaphone,No Number\n"
    )
    pairs, invalid = parse_contacts_csv(text)
    assert ("+15551234567", "Mom") in pairs
    assert ("+15559876543", "Dr. Smith") in pairs
    assert invalid == 1


def test_contact_create_via_admin(auth_client):
    resp = auth_client.post(
        "/admin/contacts/new",
        data={"phone": "5551234567", "display_name": "Mom"},
    )
    assert resp.status_code == 302
    assert count_contacts() == 1
    assert get_contact_by_phone("+15551234567")["display_name"] == "Mom"


def test_contact_create_rejects_bad_phone(auth_client):
    resp = auth_client.post(
        "/admin/contacts/new",
        data={"phone": "nope", "display_name": "Mom"},
    )
    assert resp.status_code == 200  # re-renders form with error
    assert count_contacts() == 0


def test_contact_delete_via_admin(auth_client):
    auth_client.post(
        "/admin/contacts/new",
        data={"phone": "5551234567", "display_name": "Mom"},
    )
    row = get_contact_by_phone("+15551234567")
    resp = auth_client.post(f"/admin/contacts/{row['id']}/delete")
    assert resp.status_code == 302
    assert count_contacts() == 0


def test_csv_import_via_admin(auth_client):
    csv_bytes = b"phone,display_name\n+15551234567,Mom\n5559876543,Dr. Smith\n"
    resp = auth_client.post(
        "/admin/contacts/import",
        data={"file": (io.BytesIO(csv_bytes), "contacts.csv")},
        content_type="multipart/form-data",
    )
    assert resp.status_code == 302
    assert count_contacts() == 2


def test_contact_name_used_in_inbox(auth_client, sample_recording):
    upsert_contact("+15551112222", "Grandma")
    sample_recording(caller_id="+15551112222")
    resp = auth_client.get("/admin/messages")
    assert b"Grandma" in resp.data


def test_contact_is_vip_persists_on_create(auth_client):
    resp = auth_client.post(
        "/admin/contacts/new",
        data={"phone": "5551234567", "display_name": "Mom", "is_vip": "y"},
    )
    assert resp.status_code == 302
    assert bool(get_contact_by_phone("+15551234567")["is_vip"]) is True


def test_contact_is_vip_defaults_off(auth_client):
    auth_client.post(
        "/admin/contacts/new",
        data={"phone": "5551234567", "display_name": "Mom"},
    )
    assert bool(get_contact_by_phone("+15551234567")["is_vip"]) is False


def test_contact_edit_updates_is_vip(auth_client):
    upsert_contact("+15551234567", "Mom", is_vip=True)
    row = get_contact_by_phone("+15551234567")
    # Editing without the checkbox turns it off.
    resp = auth_client.post(
        f"/admin/contacts/{row['id']}/edit",
        data={"phone": "+15551234567", "display_name": "Mom"},
    )
    assert resp.status_code == 302
    assert bool(get_contact_by_phone("+15551234567")["is_vip"]) is False
