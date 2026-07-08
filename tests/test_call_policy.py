from app.utils.call_policy import is_blocked, is_vip_contact, normalize_caller_id
from app.utils.db import upsert_blocked, upsert_contact


def test_normalize_caller_id_e164(app):
    assert normalize_caller_id("5551234567") == "+15551234567"
    assert normalize_caller_id("+15551234567") == "+15551234567"


def test_normalize_caller_id_private_values(app):
    for value in ("unknown", "anonymous", "restricted", "private", ""):
        assert normalize_caller_id(value) is None
    assert normalize_caller_id(None) is None


def test_is_blocked_exact_match(app):
    upsert_blocked("+15559998888")
    assert is_blocked("+15559998888") is True


def test_is_blocked_tail_match_without_country_code(app):
    upsert_blocked("+15559998888")
    # Caller ID shown without the +1 still matches.
    assert is_blocked("5559998888") is True


def test_is_blocked_unlisted_number(app):
    upsert_blocked("+15559998888")
    assert is_blocked("+15551112222") is False


def test_is_blocked_ignores_private_caller(app):
    upsert_blocked("+15559998888")
    assert is_blocked("anonymous") is False


def test_is_vip_contact_for_vip(app):
    upsert_contact("+15551112222", "Mom", is_vip=True)
    assert is_vip_contact("+15551112222") is True
    # Tail match works too.
    assert is_vip_contact("5551112222") is True


def test_is_vip_contact_false_for_normal_contact(app):
    upsert_contact("+15551112222", "Mom")
    assert is_vip_contact("+15551112222") is False


def test_is_vip_contact_false_for_unknown_caller(app):
    assert is_vip_contact("+15550009999") is False
