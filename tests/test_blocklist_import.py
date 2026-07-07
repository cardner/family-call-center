import app.utils.blocklist_import as blocklist_import
from app.utils.blocklist_import import (
    SEED_SOURCE,
    filter_entries,
    import_callshield_seed,
)
from app.utils.call_policy import is_blocked
from app.utils.db import count_blocked_by_source, upsert_blocked

SAMPLE_FEED = [
    {"number": "+13042635785", "type": "robocall", "reports": 453, "description": "FCC: Robocalls"},
    {"number": "5551234567", "type": "scam", "reports": 10, "description": "IRS scam"},
    {"number": "+15550001111", "type": "robocall", "reports": 1, "description": "single report"},
    {"number": "+15552223333", "type": "survey", "reports": 99, "description": "survey"},
    {"number": "not-a-number", "type": "scam", "reports": 50, "description": "junk"},
]


def test_filter_entries_keeps_only_qualified():
    kept = filter_entries(SAMPLE_FEED, min_reports=3)
    phones = {phone for phone, _, _ in kept}
    # High-report robocall and scam are kept; the scam number is normalized.
    assert "+13042635785" in phones
    assert "+15551234567" in phones
    # Below the report threshold, wrong type, and unparseable are dropped.
    assert "+15550001111" not in phones
    assert "+15552223333" not in phones
    assert len(kept) == 2


def test_filter_entries_tags_source_and_note():
    kept = filter_entries(SAMPLE_FEED, min_reports=3)
    for _, note, source in kept:
        assert source == SEED_SOURCE
        assert note  # non-empty description note


def test_import_seed_writes_rows(app, monkeypatch):
    monkeypatch.setattr(
        blocklist_import, "fetch_callshield_entries", lambda url=None: SAMPLE_FEED
    )
    result = import_callshield_seed()
    assert result["added"] == 2
    assert result["matched"] == 2
    assert count_blocked_by_source(SEED_SOURCE) == 2
    assert is_blocked("+13042635785") is True


def test_import_seed_skips_existing(app, monkeypatch):
    # A manually blocked number should not be counted as newly added, and must
    # keep its user source so it survives seed removal.
    upsert_blocked("+13042635785", note="manual", source="user")
    monkeypatch.setattr(
        blocklist_import, "fetch_callshield_entries", lambda url=None: SAMPLE_FEED
    )
    result = import_callshield_seed()
    assert result["added"] == 1
    assert result["skipped"] == 1
