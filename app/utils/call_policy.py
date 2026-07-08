"""Caller filtering applied at ``/call`` before the IVR menu.

Two independent checks decide what an incoming caller hears:

- ``is_blocked`` — the number is on the blocklist and should be rejected.
- ``is_vip_contact`` — the caller is a contact marked as VIP. VIPs bypass the
  blocklist (a number that is both VIP and blocked is still allowed through);
  they still choose a mailbox from the menu like everyone else.

Lookups reuse the same normalization and last-10-digit fallback as the contacts
address book, and the blocklist index is cached on ``flask.g`` so gating a call
reads the table only once per request.
"""

from flask import g, has_request_context

from app.utils.db import all_blocked, get_contact_by_phone
from app.utils.phone import last_ten, normalize_phone

# Caller ID values Twilio sends when the number is hidden or unavailable.
_PRIVATE_CALLER_IDS = {"unknown", "anonymous", "restricted", "private"}


def normalize_caller_id(raw):
    """Return an E.164 caller ID, or None for private/unparseable numbers."""
    if not raw:
        return None
    if str(raw).strip().lower() in _PRIVATE_CALLER_IDS:
        return None
    return normalize_phone(raw)


def _build_blocked_index():
    exact = set()
    tail = set()
    for row in all_blocked():
        phone = row["phone"]
        exact.add(phone)
        tail_key = last_ten(phone)
        if tail_key:
            tail.add(tail_key)
    return exact, tail


def _blocked_index():
    if has_request_context():
        cached = getattr(g, "_blocked_index", None)
        if cached is not None:
            return cached
        index = _build_blocked_index()
        g._blocked_index = index
        return index
    return _build_blocked_index()


def is_blocked(caller_id):
    """Return True if the caller ID matches a blocked number.

    Matches on the normalized E.164 form first, then falls back to the last ten
    digits so a stored ``+15551234567`` still blocks a caller shown as
    ``5551234567``. Private/unparseable caller IDs are never blocked.
    """
    normalized = normalize_caller_id(caller_id)
    if not normalized:
        return False
    exact, tail = _blocked_index()
    if normalized in exact:
        return True
    return last_ten(normalized) in tail


def is_vip_contact(caller_id):
    """Return True if the caller is a contact flagged as VIP."""
    normalized = normalize_caller_id(caller_id)
    if not normalized:
        return False
    contact = get_contact_by_phone(normalized)
    if contact is None:
        return False
    return bool(contact["is_vip"])
