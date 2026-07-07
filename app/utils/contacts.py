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

from flask import g, has_request_context

from app.utils.db import all_contacts
from app.utils.phone import last_ten, normalize_phone

# Display names are short labels like "Mom" or "Dr. Smith's office".
CONTACT_NAME_MAX_LENGTH = 120

# Header cells we skip if the CSV includes a header row.
_HEADER_PHONE = {"phone", "number", "phone_number", "phonenumber"}
_HEADER_NAME = {"display_name", "name", "contact", "displayname"}


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
    """Parse CSV text into ``(pairs, invalid_count)``.

    Accepts an optional ``phone,display_name`` header row. Blank lines are
    skipped. Rows whose phone cannot be normalized or whose name is empty are
    counted as invalid. Returned pairs use normalized E.164 phones, ready for
    ``bulk_upsert_contacts``.
    """
    pairs = []
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
        if phone_raw.lower() in _HEADER_PHONE and name.lower() in _HEADER_NAME:
            continue
        normalized = normalize_phone(phone_raw)
        if not normalized or not name:
            invalid += 1
            continue
        pairs.append((normalized, name[:CONTACT_NAME_MAX_LENGTH]))
    return pairs, invalid
