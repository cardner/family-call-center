"""Optional starter blocklist import from a public spam-number feed.

The feed is the community-maintained CallShield database (MIT licensed), which
aggregates FCC complaints, FTC Do Not Call reports, and community submissions in
E.164 form. Importing is always an explicit admin action; nothing is fetched or
installed automatically.

To limit false positives, imported entries are filtered by report count and
call type before they are written with ``source='seed:callshield'`` so the whole
set can be removed later without touching manually blocked numbers.
"""

import logging

import requests

from app.utils.db import bulk_upsert_blocked
from app.utils.phone import normalize_phone

logger = logging.getLogger(__name__)

SEED_SOURCE = "seed:callshield"

CALLSHIELD_FEED_URL = (
    "https://raw.githubusercontent.com/SysAdminDoc/CallShield/master/data/spam_numbers.json"
)

# Only import numbers reported at least this many times and of these call types,
# which keeps well-known robocallers/scammers while dropping one-off reports.
DEFAULT_MIN_REPORTS = 3
DEFAULT_TYPES = ("robocall", "scam", "telemarketer")

# Guard against an unexpectedly large or slow download.
_FETCH_TIMEOUT_SECONDS = 30
_NOTE_MAX_LENGTH = 200


class BlocklistImportError(Exception):
    """Raised when the starter feed cannot be fetched or parsed."""


def fetch_callshield_entries(url=CALLSHIELD_FEED_URL):
    """Fetch and return the raw list of entries from the CallShield feed."""
    try:
        response = requests.get(url, timeout=_FETCH_TIMEOUT_SECONDS)
        response.raise_for_status()
        data = response.json()
    except (requests.RequestException, ValueError) as exc:
        raise BlocklistImportError(
            "Could not download the starter blocklist. Check your connection and "
            "try again."
        ) from exc

    entries = data.get("numbers") if isinstance(data, dict) else data
    if not isinstance(entries, list):
        raise BlocklistImportError("Starter blocklist feed was not in the expected format.")
    return entries


def filter_entries(entries, *, min_reports=DEFAULT_MIN_REPORTS, types=DEFAULT_TYPES):
    """Reduce raw feed entries to ``(phone, note, source)`` tuples worth blocking.

    Entries are kept only when the call type matches and the report count meets
    the threshold. Phones are normalized to E.164; unparseable ones are dropped.
    """
    allowed_types = {t.lower() for t in types}
    kept = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        call_type = str(entry.get("type", "")).lower()
        if allowed_types and call_type not in allowed_types:
            continue
        try:
            reports = int(entry.get("reports", 0))
        except (TypeError, ValueError):
            reports = 0
        if reports < min_reports:
            continue
        phone = normalize_phone(entry.get("number"))
        if not phone:
            continue
        description = str(entry.get("description") or call_type or "spam").strip()
        note = f"{call_type or 'spam'}: {description}"[:_NOTE_MAX_LENGTH]
        kept.append((phone, note, SEED_SOURCE))
    return kept


def import_callshield_seed(*, min_reports=DEFAULT_MIN_REPORTS, url=CALLSHIELD_FEED_URL):
    """Fetch, filter, and store the starter blocklist.

    Returns a summary dict with the counts of numbers ``added`` (newly written),
    ``matched`` (passed the filter), and ``skipped`` (already blocked).
    """
    entries = fetch_callshield_entries(url=url)
    filtered = filter_entries(entries, min_reports=min_reports)
    added = bulk_upsert_blocked(filtered) if filtered else 0
    matched = len(filtered)
    logger.info("Starter blocklist import: matched=%d added=%d", matched, added)
    return {"added": added, "matched": matched, "skipped": matched - added}
