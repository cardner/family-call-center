from app.utils.voices import (
    ALLOWED_IVR_VOICES,
    DEFAULT_IVR_VOICE,
    ivr_voice_gender,
    ivr_voice_grouped_choices,
    ivr_voice_language,
    ivr_voice_meta,
    ivr_voice_region,
    normalize_ivr_voice,
)


def test_default_voice_is_allowed():
    assert DEFAULT_IVR_VOICE in ALLOWED_IVR_VOICES


def test_normalize_ivr_voice_accepts_known_voice():
    assert normalize_ivr_voice("Google.en-GB-Neural2-N") == "Google.en-GB-Neural2-N"


def test_normalize_ivr_voice_rejects_unknown():
    assert normalize_ivr_voice("Polly.Joanna-Neural") == DEFAULT_IVR_VOICE
    assert normalize_ivr_voice("") == DEFAULT_IVR_VOICE


def test_ivr_voice_language():
    assert ivr_voice_language("Google.en-US-Neural2-D") == "en-US"
    assert ivr_voice_language("Google.en-GB-Neural2-O") == "en-GB"


def test_ivr_voice_gender():
    assert ivr_voice_gender("Google.en-US-Neural2-D") == "male"
    assert ivr_voice_gender("Google.en-US-Neural2-C") == "female"


def test_ivr_voice_region():
    assert ivr_voice_region("Google.en-US-Neural2-A") == "US"
    assert ivr_voice_region("Google.en-GB-Neural2-N") == "UK"


def test_grouped_choices_structure():
    groups = ivr_voice_grouped_choices()
    assert list(groups.keys()) == [
        "US English — Male",
        "US English — Female",
        "UK English — Male",
        "UK English — Female",
    ]
    # Every catalog voice appears exactly once across the groups.
    flat = [value for options in groups.values() for value, _ in options]
    assert sorted(flat) == sorted(ALLOWED_IVR_VOICES)
    assert len(flat) == len(ALLOWED_IVR_VOICES)


def test_grouped_choices_group_membership():
    groups = ivr_voice_grouped_choices()
    us_male = dict(groups["US English — Male"])
    assert "Google.en-US-Neural2-D" in us_male
    uk_female = dict(groups["UK English — Female"])
    assert "Google.en-GB-Neural2-N" in uk_female


def test_ivr_voice_meta_shape():
    meta = ivr_voice_meta()
    assert set(meta.keys()) == set(ALLOWED_IVR_VOICES)
    entry = meta["Google.en-GB-Neural2-N"]
    assert entry == {
        "lang": "en-GB",
        "gender": "female",
        "region": "UK",
        "label": "Neural2 N",
    }


def test_settings_post_saves_grouped_voice(auth_client):
    from tests.helpers import valid_settings

    data = valid_settings(ivr_voice="Google.en-GB-Neural2-O")
    resp = auth_client.post("/admin/settings", data=data, follow_redirects=True)
    assert resp.status_code == 200

    with auth_client.application.test_request_context():
        from app.utils.twiml import get_ivr_voice, main_menu_twiml

        assert get_ivr_voice() == "Google.en-GB-Neural2-O"
        twiml = main_menu_twiml().get_data(as_text=True)
    assert 'voice="Google.en-GB-Neural2-O"' in twiml
    assert 'language="en-GB"' in twiml
