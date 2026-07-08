"""Per-recipient voicemail boxes.

Each box maps a single menu digit to a mailbox with its own optional prompt,
thank-you message, and SMS notification recipients. The four family boxes
(Family, Cody, Ryan, Cory) are seeded on first run and edited from the admin UI.

Prompt, thank-you, and notification fields are treated as *overrides*: when a
box leaves one blank it falls back to the global Setting of the same name, so a
fresh install behaves exactly like the previous single-mailbox setup.
"""

import re

from app.utils.db import get_connection
from app.utils.settings import is_valid_e164, parse_phone_numbers

# Slug: lowercase letters, digits, and hyphens. Used in the /voicemail?box=slug
# query parameter and as the stable key for lookups.
BOX_SLUG_MAX_LENGTH = 32
_SLUG_RE = re.compile(r"^[a-z0-9-]{1,%d}$" % BOX_SLUG_MAX_LENGTH)

# A menu digit is a single 0-9 character.
_DIGIT_RE = re.compile(r"^[0-9]$")

DEFAULT_BOX_SLUG = "family"

DEFAULT_BOXES = (
    {"slug": "family", "display_name": "Family", "extension_digit": "1"},
    {"slug": "cody", "display_name": "Cody", "extension_digit": "2"},
    {"slug": "ryan", "display_name": "Ryan", "extension_digit": "3"},
    {"slug": "cory", "display_name": "Cory", "extension_digit": "4"},
)

# Columns an admin may edit on a box.
_EDITABLE_COLUMNS = (
    "display_name",
    "extension_digit",
    "voicemail_prompt",
    "voicemail_thanks",
    "notify_phone_numbers",
    "enabled",
)


def is_valid_slug(slug):
    return bool(_SLUG_RE.match(slug or ""))


def seed_default_boxes():
    """Insert the four default boxes if none exist, then backfill recordings.

    New boxes start with blank prompt/thanks/notify overrides so they inherit
    the global Settings. Existing recordings (created before boxes existed) are
    assigned to the Family box so they still appear in the inbox.
    """
    with get_connection() as conn:
        existing = conn.execute("SELECT COUNT(*) AS n FROM voicemail_boxes").fetchone()
        if existing["n"] == 0:
            for order, box in enumerate(DEFAULT_BOXES):
                conn.execute(
                    """
                    INSERT INTO voicemail_boxes
                        (slug, display_name, extension_digit, sort_order)
                    VALUES (?, ?, ?, ?)
                    """,
                    (box["slug"], box["display_name"], box["extension_digit"], order),
                )
        family = conn.execute(
            "SELECT id FROM voicemail_boxes WHERE slug = ?", (DEFAULT_BOX_SLUG,)
        ).fetchone()
        if family is not None:
            conn.execute(
                "UPDATE recordings SET box_id = ? WHERE box_id IS NULL",
                (family["id"],),
            )
        conn.commit()


def list_boxes(enabled_only=False):
    """Return boxes ordered by their menu position."""
    where = "WHERE enabled = 1" if enabled_only else ""
    with get_connection() as conn:
        return conn.execute(
            f"SELECT * FROM voicemail_boxes {where} "
            "ORDER BY sort_order ASC, id ASC"
        ).fetchall()


def get_box(box_id):
    with get_connection() as conn:
        return conn.execute(
            "SELECT * FROM voicemail_boxes WHERE id = ?", (box_id,)
        ).fetchone()


def get_box_by_slug(slug):
    if not slug:
        return None
    with get_connection() as conn:
        return conn.execute(
            "SELECT * FROM voicemail_boxes WHERE slug = ?", (slug,)
        ).fetchone()


def get_box_by_digit(digit):
    """Return the enabled box mapped to ``digit``, or None."""
    if not _DIGIT_RE.match(digit or ""):
        return None
    with get_connection() as conn:
        return conn.execute(
            "SELECT * FROM voicemail_boxes WHERE extension_digit = ? AND enabled = 1",
            (digit,),
        ).fetchone()


def get_default_box():
    """Return the fallback box used when none is specified (Family)."""
    return get_box_by_slug(DEFAULT_BOX_SLUG) or _first_box()


def _first_box():
    boxes = list_boxes(enabled_only=True)
    return boxes[0] if boxes else None


def get_box_notify_phone_numbers(box):
    """Return a box's own valid SMS recipients (empty list if it inherits)."""
    if box is None:
        return []
    raw = box["notify_phone_numbers"]
    return [number for number in parse_phone_numbers(raw) if is_valid_e164(number)]


def update_box(box_id, **fields):
    """Update the editable columns supplied in ``fields`` for one box."""
    columns = [name for name in _EDITABLE_COLUMNS if name in fields]
    if not columns:
        return
    assignments = ", ".join(f"{name} = ?" for name in columns)
    values = [fields[name] for name in columns]
    with get_connection() as conn:
        conn.execute(
            f"UPDATE voicemail_boxes SET {assignments} WHERE id = ?",
            values + [box_id],
        )
        conn.commit()
