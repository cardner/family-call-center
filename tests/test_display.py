from datetime import datetime
from zoneinfo import ZoneInfo

from app.utils.display import format_recorded_at, parse_recorded_at

ET = ZoneInfo("America/New_York")


def test_parse_recorded_at_accepts_z_suffix():
    dt = parse_recorded_at("2026-07-06T18:14:00Z")
    assert dt is not None
    assert dt.tzinfo is not None


def test_format_recorded_at_today():
    now = datetime(2026, 7, 6, 20, 0, tzinfo=ET)
    assert (
        format_recorded_at("2026-07-06T18:14:00+00:00", now=now, tz=ET)
        == "Today 2:14 PM"
    )


def test_format_recorded_at_yesterday():
    now = datetime(2026, 7, 6, 20, 0, tzinfo=ET)
    assert (
        format_recorded_at("2026-07-05T18:14:00+00:00", now=now, tz=ET)
        == "Yesterday 2:14 PM"
    )


def test_format_recorded_at_same_year():
    now = datetime(2026, 7, 6, 20, 0, tzinfo=ET)
    assert (
        format_recorded_at("2026-06-15T18:14:00+00:00", now=now, tz=ET)
        == "Jun 15 · 2:14 PM"
    )


def test_format_recorded_at_prior_year():
    now = datetime(2026, 7, 6, 20, 0, tzinfo=ET)
    assert (
        format_recorded_at("2025-12-31T23:00:00+00:00", now=now, tz=ET)
        == "Dec 31, 2025 · 6:00 PM"
    )


def test_format_recorded_at_midnight_uses_12_hour_clock():
    now = datetime(2026, 7, 6, 12, 0, tzinfo=ET)
    assert (
        format_recorded_at("2026-07-06T04:00:00+00:00", now=now, tz=ET)
        == "Today 12:00 AM"
    )


def test_format_recorded_at_empty():
    assert format_recorded_at("") == "—"
    assert format_recorded_at(None) == "—"


def test_format_recorded_at_invalid():
    assert format_recorded_at("not-a-date") == "not-a-date"
