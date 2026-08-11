"""Resolve caller IDs to friendly contact names.

The address book (``contacts`` table) maps normalized phone numbers to display
names like "Mom" or "Dr. Smith's office". Resolution tries an exact normalized
match first, then falls back to matching the last 10 digits so a stored
``+15551234567`` still matches a caller shown as ``5551234567``.

Within a request the contact index is cached on ``flask.g`` so rendering an
inbox of many rows only reads the contacts table once.
"""

import csv
import io
import re

from flask import g, has_request_context

from app.utils.boxes import DEFAULT_BOX_SLUG
from app.utils.db import (
    all_contacts,
    get_contact_by_box_id,
    get_parent_contacts_for_box,
    list_admin_contacts,
    list_notification_contacts,
)
from app.utils.phone import last_ten, normalize_phone

# Display names are short labels like "Mom" or "Dr. Smith's office".
CONTACT_NAME_MAX_LENGTH = 120

# Email addresses are capped near the RFC 5321 practical limit.
EMAIL_MAX_LENGTH = 254

# Strict single-address pattern. It rejects whitespace, commas, and angle
# brackets so a stored value can never smuggle extra recipients or CRLF header
# injection into an outbound email.
_EMAIL_RE = re.compile(r"^[^\s@,<>\"]+@[^\s@,<>\"]+\.[^\s@,<>\"]+$")

# Header cells we skip if the CSV includes a header row.
_HEADER_PHONE = {"phone", "number", "phone_number", "phonenumber"}
_HEADER_NAME = {"display_name", "name", "contact", "displayname"}
_HEADER_EMAIL = {"email", "email_address", "e-mail"}


def is_valid_email(address):
    """Return True if ``address`` is a single, plausible email address."""
    address = (address or "").strip()
    if not address or len(address) > EMAIL_MAX_LENGTH:
        return False
    return bool(_EMAIL_RE.match(address))


def normalize_email(address):
    """Trim and lowercase an email, or return '' when blank/invalid."""
    address = (address or "").strip().lower()
    return address if is_valid_email(address) else ""


def mask_email(address):
    """Mask an address for display, e.g. ``j…@example.com``."""
    address = (address or "").strip()
    if "@" not in address:
        return address
    local, _, domain = address.partition("@")
    if len(local) <= 1:
        return f"…@{domain}"
    return f"{local[0]}…@{domain}"


def _build_index():
    exact = {}
    tail = {}
    for contact in all_contacts():
        phone = contact["phone"]
        name = contact["display_name"]
        exact[phone] = name
        tail_key = last_ten(phone)
        if tail_key:
            tail.setdefault(tail_key, name)
    return exact, tail


def _contact_index():
    if has_request_context():
        cached = getattr(g, "_contact_index", None)
        if cached is not None:
            return cached
        index = _build_index()
        g._contact_index = index
        return index
    return _build_index()


def resolve_caller_display(caller_id):
    """Return ``{"phone": str, "name": str | None}`` for a caller ID.

    ``name`` is None when no contact matches. ``phone`` is the original caller ID
    (unchanged) so it can still be shown alongside the name.
    """
    original = caller_id or ""
    if not original or original == "unknown":
        return {"phone": original, "name": None}

    exact, tail = _contact_index()
    normalized = normalize_phone(original)
    name = None
    if normalized:
        name = exact.get(normalized)
    if not name:
        name = tail.get(last_ten(original))
    return {"phone": original, "name": name}


def caller_label(caller_id):
    """Human-friendly label: the contact name if known, else the raw caller ID."""
    display = resolve_caller_display(caller_id)
    if display["name"]:
        return display["name"]
    return display["phone"] or "unknown"


def parse_contacts_csv(raw_text):
    """Parse CSV text into ``(rows, invalid_count)``.

    Accepts an optional ``phone,display_name,email`` header row (email is
    optional). Blank lines are skipped. Rows whose phone cannot be normalized or
    whose name is empty are counted as invalid. An invalid email is dropped (set
    to '') rather than failing the whole row. Returned rows are
    ``(phone, display_name, email)`` triples ready for ``bulk_upsert_contacts``.
    """
    rows = []
    invalid = 0
    reader = csv.reader(io.StringIO(raw_text))
    for row in reader:
        cells = [cell.strip() for cell in row]
        if not any(cells):
            continue
        if len(cells) < 2:
            invalid += 1
            continue
        phone_raw, name = cells[0], cells[1]
        email_raw = cells[2] if len(cells) >= 3 else ""
        if (
            phone_raw.lower() in _HEADER_PHONE
            and name.lower() in _HEADER_NAME
        ):
            continue
        normalized = normalize_phone(phone_raw)
        if not normalized or not name:
            invalid += 1
            continue
        rows.append(
            (normalized, name[:CONTACT_NAME_MAX_LENGTH], normalize_email(email_raw))
        )
    return rows, invalid


# --- Email notification routing --------------------------------------------


def get_admin_notification_emails():
    """Return deduped, valid emails for every admin contact."""
    emails = []
    for contact in list_admin_contacts():
        email = normalize_email(contact["email"])
        if email and email not in emails:
            emails.append(email)
    return emails


def get_box_owner_email(box):
    """Return the valid email of the contact linked to ``box``, or None."""
    if box is None:
        return None
    contact = get_contact_by_box_id(box["id"])
    if contact is None:
        return None
    email = normalize_email(contact["email"])
    return email or None


def get_parent_emails_for_box(box):
    """Return deduped, valid emails of the parents linked to a child mailbox."""
    if box is None:
        return []
    emails = []
    for contact in get_parent_contacts_for_box(box["id"]):
        email = normalize_email(contact["email"])
        if email and email not in emails:
            emails.append(email)
    return emails


def resolve_email_recipients(box):
    """Return the list of recipient emails for a voicemail in ``box``.

    The Family box (and a missing box) routes to all admins. Every other box
    routes to the single contact linked to it; when the box is flagged as a
    child mailbox, the parent accounts assigned to it are added as well.
    """
    if box is None or box["slug"] == DEFAULT_BOX_SLUG:
        return get_admin_notification_emails()

    recipients = []
    owner_email = get_box_owner_email(box)
    if owner_email:
        recipients.append(owner_email)
    if box["is_child"]:
        for email in get_parent_emails_for_box(box):
            if email not in recipients:
                recipients.append(email)
    return recipients


def get_all_notification_emails():
    """Return every deduped recipient email (admins + box owners)."""
    emails = []
    for contact in list_notification_contacts():
        email = normalize_email(contact["email"])
        if email and email not in emails:
            emails.append(email)
    return emails


def count_notification_recipients():
    """Count the distinct email addresses that can receive alerts."""
    return len(get_all_notification_emails())
