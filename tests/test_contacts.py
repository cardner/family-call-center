import io

from app.utils.boxes import get_box_by_slug
from app.utils.contacts import (
    get_admin_notification_emails,
    get_parent_notification_emails,
    is_valid_email,
    mask_email,
    parse_contacts_csv,
    resolve_caller_display,
    resolve_email_recipients,
)
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
        "phone,display_name,email\n"
        "+15551234567,Mom,mom@example.com\n"
        "5559876543,Dr. Smith\n"
        "\n"
        "notaphone,No Number\n"
    )
    rows, invalid = parse_contacts_csv(text)
    assert ("+15551234567", "Mom", "mom@example.com") in rows
    assert ("+15559876543", "Dr. Smith", "") in rows
    assert invalid == 1


def test_parse_csv_drops_invalid_email():
    rows, invalid = parse_contacts_csv("+15551234567,Mom,not-an-email\n")
    assert rows == [("+15551234567", "Mom", "")]
    assert invalid == 0


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


# --- Email notification routing --------------------------------------------


def test_is_valid_email():
    assert is_valid_email("you@example.com")
    assert not is_valid_email("nope")
    assert not is_valid_email("a@b")
    assert not is_valid_email("a b@example.com")
    assert not is_valid_email("a@example.com,b@example.com")


def test_mask_email():
    assert mask_email("ryan@example.com") == "r…@example.com"
    assert mask_email("r@example.com") == "…@example.com"


def test_admin_emails_deduped_and_validated(app):
    upsert_contact("+15550000001", "Ryan", is_admin=True, email="ryan@example.com")
    upsert_contact("+15550000002", "NoEmail", is_admin=True, email="")
    assert get_admin_notification_emails() == ["ryan@example.com"]


def test_resolve_recipients_family_vs_box(app):
    cody = get_box_by_slug("cody")
    upsert_contact("+15550000001", "Ryan", is_admin=True, email="ryan@example.com")
    upsert_contact("+15550000002", "Cody", email="cody@example.com", box_id=cody["id"])

    assert resolve_email_recipients(get_box_by_slug("family")) == ["ryan@example.com"]
    assert resolve_email_recipients(cody) == ["cody@example.com"]


def test_parent_emails_deduped_and_validated(app):
    upsert_contact(
        "+15550000001", "Ryan", is_parent=True, email="ryan@example.com"
    )
    upsert_contact("+15550000002", "NoEmail", is_parent=True, email="")
    assert get_parent_notification_emails() == ["ryan@example.com"]


def test_child_box_notifies_parents(app):
    cody = get_box_by_slug("cody")
    upsert_contact("+15550000001", "Ryan", is_parent=True, email="ryan@example.com")
    upsert_contact(
        "+15550000002",
        "Cody",
        email="cody@example.com",
        box_id=cody["id"],
        is_child=True,
    )
    # The child owner plus every parent are notified for the child's box.
    assert resolve_email_recipients(cody) == ["cody@example.com", "ryan@example.com"]


def test_non_child_box_does_not_notify_parents(app):
    cody = get_box_by_slug("cody")
    upsert_contact("+15550000001", "Ryan", is_parent=True, email="ryan@example.com")
    upsert_contact("+15550000002", "Cody", email="cody@example.com", box_id=cody["id"])
    assert resolve_email_recipients(cody) == ["cody@example.com"]


def test_child_box_notifies_parents_without_owner_email(app):
    cody = get_box_by_slug("cody")
    upsert_contact("+15550000001", "Ryan", is_parent=True, email="ryan@example.com")
    upsert_contact("+15550000002", "Cody", box_id=cody["id"], is_child=True)
    assert resolve_email_recipients(cody) == ["ryan@example.com"]


def test_child_parent_overlap_deduped(app):
    cody = get_box_by_slug("cody")
    # A parent who also owns the child box should only appear once.
    upsert_contact(
        "+15550000002",
        "Cody",
        email="cody@example.com",
        box_id=cody["id"],
        is_child=True,
    )
    upsert_contact("+15550000001", "Cody2", is_parent=True, email="cody@example.com")
    assert resolve_email_recipients(cody) == ["cody@example.com"]


def test_contact_create_parent_via_admin(auth_client):
    resp = auth_client.post(
        "/admin/contacts/new",
        data={
            "phone": "5551234567",
            "display_name": "Ryan",
            "email": "ryan@example.com",
            "is_parent": "y",
        },
    )
    assert resp.status_code == 302
    assert bool(get_contact_by_phone("+15551234567")["is_parent"]) is True


def test_contact_child_requires_box(auth_client):
    resp = auth_client.post(
        "/admin/contacts/new",
        data={
            "phone": "5551234567",
            "display_name": "Cody",
            "email": "cody@example.com",
            "is_child": "y",
        },
    )
    assert resp.status_code == 200  # re-renders with an error
    assert count_contacts() == 0


def test_contact_parent_requires_email(auth_client):
    resp = auth_client.post(
        "/admin/contacts/new",
        data={"phone": "5551234567", "display_name": "Ryan", "is_parent": "y"},
    )
    assert resp.status_code == 200
    assert count_contacts() == 0


def test_contact_create_with_email_and_admin(auth_client):
    resp = auth_client.post(
        "/admin/contacts/new",
        data={
            "phone": "5551234567",
            "display_name": "Ryan",
            "email": "ryan@example.com",
            "is_admin": "y",
        },
    )
    assert resp.status_code == 302
    row = get_contact_by_phone("+15551234567")
    assert row["email"] == "ryan@example.com"
    assert bool(row["is_admin"]) is True


def test_contact_admin_requires_email(auth_client):
    resp = auth_client.post(
        "/admin/contacts/new",
        data={"phone": "5551234567", "display_name": "Ryan", "is_admin": "y"},
    )
    assert resp.status_code == 200  # re-renders with an error
    assert count_contacts() == 0


def test_contact_link_box(auth_client):
    cody = get_box_by_slug("cody")
    resp = auth_client.post(
        "/admin/contacts/new",
        data={
            "phone": "5551234567",
            "display_name": "Cody",
            "email": "cody@example.com",
            "box_id": str(cody["id"]),
        },
    )
    assert resp.status_code == 302
    assert get_contact_by_phone("+15551234567")["box_id"] == cody["id"]


def test_contact_box_link_must_be_unique(auth_client):
    cody = get_box_by_slug("cody")
    upsert_contact(
        "+15550000001", "Cody", email="cody@example.com", box_id=cody["id"]
    )
    resp = auth_client.post(
        "/admin/contacts/new",
        data={
            "phone": "5559998888",
            "display_name": "Impostor",
            "email": "impostor@example.com",
            "box_id": str(cody["id"]),
        },
    )
    assert resp.status_code == 200  # re-renders with an error
    assert b"already linked" in resp.data
    assert get_contact_by_phone("+15559998888") is None


def test_csv_import_stores_email(auth_client):
    csv_bytes = b"phone,display_name,email\n+15551234567,Mom,mom@example.com\n"
    resp = auth_client.post(
        "/admin/contacts/import",
        data={"file": (io.BytesIO(csv_bytes), "contacts.csv")},
        content_type="multipart/form-data",
    )
    assert resp.status_code == 302
    assert get_contact_by_phone("+15551234567")["email"] == "mom@example.com"
