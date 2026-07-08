"""Personalize spoken IVR prompts using the caller's contact name.

When the admin enables personalized greetings, the main menu greeting and the
voicemail prompt are tailored to the caller if their number matches a contact.
Admins can place a ``{name}`` token anywhere in a prompt to control where the
name appears; if the token is absent we prepend a friendly salutation instead.
When the feature is off, no contact matches, or the caller ID is private, any
``{name}`` token is removed and the surrounding salutation is tidied up.
"""

import re

from app.utils.contacts import CONTACT_NAME_MAX_LENGTH, resolve_caller_display
from app.utils.settings import (
    IVR_TEXT_MAX_LENGTH,
    get_setting,
    is_personalized_greeting_enabled,
)
from app.utils.validation import sanitize_text

_NAME_PLACEHOLDER = "{name}"

# Salutations left dangling once a {name} token is removed, e.g. "Hi {name}."
# becomes "Hi ." — strip the leading salutation so the prompt still reads well.
_ORPHAN_SALUTATION_RE = re.compile(
    r"^\s*(?:hi|hello|hey|thanks for calling)\s*[.,!]*\s*", re.IGNORECASE
)
_SPACE_BEFORE_PUNCT_RE = re.compile(r"\s+([.,!?])")
_MULTISPACE_RE = re.compile(r"\s{2,}")


def _strip_name_placeholder(text):
    """Remove any ``{name}`` token and clean up the orphaned phrasing."""
    if _NAME_PLACEHOLDER not in text:
        return text
    cleaned = text.replace(_NAME_PLACEHOLDER, "")
    cleaned = _ORPHAN_SALUTATION_RE.sub("", cleaned)
    cleaned = _SPACE_BEFORE_PUNCT_RE.sub(r"\1", cleaned)
    cleaned = _MULTISPACE_RE.sub(" ", cleaned)
    return cleaned.strip()


def _personalize_prompt(setting_key, caller_id, auto_prefix_template):
    base_text = get_setting(setting_key)

    if not is_personalized_greeting_enabled():
        return _strip_name_placeholder(base_text)

    name = resolve_caller_display(caller_id).get("name")
    if name:
        name = sanitize_text(name, CONTACT_NAME_MAX_LENGTH)
    if not name:
        return _strip_name_placeholder(base_text)

    if _NAME_PLACEHOLDER in base_text:
        result = base_text.replace(_NAME_PLACEHOLDER, name)
    else:
        result = auto_prefix_template.format(name=name) + base_text
    return result[:IVR_TEXT_MAX_LENGTH]


def format_greeting(caller_id=None):
    """Return the main menu greeting, personalized when enabled and known."""
    return _personalize_prompt(
        "greeting", caller_id, 'Hi {name}. <break time="200ms"/> '
    )


def format_voicemail_prompt(caller_id=None):
    """Return the voicemail prompt, personalized when enabled and known."""
    return _personalize_prompt(
        "voicemail_prompt",
        caller_id,
        'Thanks for calling {name}. <break time="200ms"/> ',
    )
