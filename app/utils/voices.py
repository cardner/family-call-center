"""Twilio neural English voices (Google Neural2) for the IVR.

Voices are exposed in the admin Settings dropdown grouped by region and gender.
The stored value is the full Twilio voice id (e.g. ``Google.en-US-Neural2-D``),
which is what the live ``<Say>`` verb uses. Browser prompt preview uses the
per-voice metadata (language + gender) to pick an approximate local voice.
"""

DEFAULT_IVR_VOICE = "Google.en-US-Neural2-D"

# voice_id, short_label, language (BCP-47), region, gender
_NEURAL_ENGLISH_VOICES = (
    ("Google.en-US-Neural2-A", "Neural2 A", "en-US", "US", "male"),
    ("Google.en-US-Neural2-D", "Neural2 D", "en-US", "US", "male"),
    ("Google.en-US-Neural2-I", "Neural2 I", "en-US", "US", "male"),
    ("Google.en-US-Neural2-J", "Neural2 J", "en-US", "US", "male"),
    ("Google.en-US-Neural2-C", "Neural2 C", "en-US", "US", "female"),
    ("Google.en-US-Neural2-E", "Neural2 E", "en-US", "US", "female"),
    ("Google.en-US-Neural2-F", "Neural2 F", "en-US", "US", "female"),
    ("Google.en-US-Neural2-G", "Neural2 G", "en-US", "US", "female"),
    ("Google.en-US-Neural2-H", "Neural2 H", "en-US", "US", "female"),
    ("Google.en-GB-Neural2-O", "Neural2 O", "en-GB", "UK", "male"),
    ("Google.en-GB-Neural2-N", "Neural2 N", "en-GB", "UK", "female"),
)

ALLOWED_IVR_VOICES = frozenset(voice_id for voice_id, *_ in _NEURAL_ENGLISH_VOICES)

# Dropdown group order: region first, then gender within each region.
_GROUP_ORDER = (
    ("US", "male", "US English — Male"),
    ("US", "female", "US English — Female"),
    ("UK", "male", "UK English — Male"),
    ("UK", "female", "UK English — Female"),
)


def normalize_ivr_voice(voice_id):
    """Return a valid Twilio voice id, falling back to the default."""
    if voice_id in ALLOWED_IVR_VOICES:
        return voice_id
    return DEFAULT_IVR_VOICE


def ivr_voice_language(voice_id):
    """Return the BCP-47 language code for a Twilio voice id."""
    for vid, _, language, _, _ in _NEURAL_ENGLISH_VOICES:
        if vid == voice_id:
            return language
    return "en-US"


def ivr_voice_gender(voice_id):
    """Return ``"male"`` or ``"female"`` for a Twilio voice id."""
    for vid, _, _, _, gender in _NEURAL_ENGLISH_VOICES:
        if vid == voice_id:
            return gender
    return "male"


def ivr_voice_region(voice_id):
    """Return ``"US"`` or ``"UK"`` for a Twilio voice id."""
    for vid, _, _, region, _ in _NEURAL_ENGLISH_VOICES:
        if vid == voice_id:
            return region
    return "US"


def ivr_voice_grouped_choices():
    """Return WTForms optgroup choices keyed by region+gender group label.

    WTForms renders and validates ``<optgroup>`` selects from a dict mapping a
    group label to a list of ``(value, label)`` pairs.
    """
    groups = {}
    for region, gender, group_label in _GROUP_ORDER:
        options = [
            (vid, short_label)
            for vid, short_label, _, r, g in _NEURAL_ENGLISH_VOICES
            if r == region and g == gender
        ]
        if options:
            groups[group_label] = options
    return groups


def ivr_voice_meta():
    """Return a voice-id keyed dict of preview metadata for the browser."""
    return {
        vid: {
            "lang": language,
            "gender": gender,
            "region": region,
            "label": short_label,
        }
        for vid, short_label, language, region, gender in _NEURAL_ENGLISH_VOICES
    }
