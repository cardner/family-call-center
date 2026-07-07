from datetime import datetime, timedelta, timezone


def _local_timezone(tz=None):
    if tz is not None:
        return tz
    return datetime.now().astimezone().tzinfo


def parse_recorded_at(value):
    """Parse an ISO timestamp stored in UTC into an aware datetime."""
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except (TypeError, ValueError, AttributeError):
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _format_time_12h(dt):
    hour = dt.hour % 12 or 12
    return f"{hour}:{dt.strftime('%M')} {dt.strftime('%p')}"


def format_recorded_at(value, *, now=None, tz=None):
    """Format an ISO UTC timestamp for the admin UI in local time.

    Examples: "Today 2:14 PM", "Yesterday 9:05 AM", "Jun 15 · 2:14 PM".
    ``tz`` is for tests; production uses the host/container local timezone.
    """
    dt = parse_recorded_at(value)
    if dt is None:
        return "—" if not value else str(value)

    local_tz = _local_timezone(tz)
    local_dt = dt.astimezone(local_tz)
    ref = (now or datetime.now(timezone.utc)).astimezone(local_tz)
    local_date = local_dt.date()
    ref_date = ref.date()
    time_str = _format_time_12h(local_dt)

    if local_date == ref_date:
        return f"Today {time_str}"
    if local_date == ref_date - timedelta(days=1):
        return f"Yesterday {time_str}"
    if local_dt.year == ref.year:
        return f"{local_dt.strftime('%b')} {local_dt.day} · {time_str}"
    return f"{local_dt.strftime('%b')} {local_dt.day}, {local_dt.year} · {time_str}"
