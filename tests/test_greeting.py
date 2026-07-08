from app.utils.db import upsert_contact
from app.utils.greeting import format_greeting, format_voicemail_prompt
from app.utils.settings import set_setting


def _enable():
    set_setting("personalized_greeting_enabled", "true")


def test_greeting_unchanged_when_feature_off(app):
    upsert_contact("+15551112222", "Mom")
    set_setting("greeting", "Hi {name}. Welcome.")
    result = format_greeting("+15551112222")
    assert "{name}" not in result
    assert "Mom" not in result
    assert "Welcome." in result


def test_greeting_substitutes_placeholder(app):
    _enable()
    upsert_contact("+15551112222", "Mom")
    set_setting("greeting", "Hi {name}. Welcome.")
    assert format_greeting("+15551112222") == "Hi Mom. Welcome."


def test_greeting_auto_prefix_when_no_placeholder(app):
    _enable()
    upsert_contact("+15551112222", "Mom")
    set_setting("greeting", "Welcome. Press 1.")
    result = format_greeting("+15551112222")
    assert result.startswith("Hi Mom.")
    assert "Welcome. Press 1." in result


def test_greeting_strips_placeholder_for_unknown_caller(app):
    _enable()
    set_setting("greeting", "Hi {name}. Welcome.")
    result = format_greeting("+15559990000")
    assert "{name}" not in result
    assert result == "Welcome."


def test_greeting_normal_for_private_caller(app):
    _enable()
    upsert_contact("+15551112222", "Mom")
    set_setting("greeting", "Hi {name}. Welcome.")
    for private in ("anonymous", "unknown", ""):
        assert format_greeting(private) == "Welcome."


def test_voicemail_auto_prefix_when_no_placeholder(app):
    _enable()
    upsert_contact("+15551112222", "Mom")
    set_setting("voicemail_prompt", "Please leave a message.")
    result = format_voicemail_prompt("+15551112222")
    assert result.startswith("Thanks for calling Mom.")
    assert "Please leave a message." in result


def test_voicemail_substitutes_placeholder(app):
    _enable()
    upsert_contact("+15551112222", "Mom")
    set_setting("voicemail_prompt", "Hey {name}, leave a message.")
    assert format_voicemail_prompt("+15551112222") == "Hey Mom, leave a message."


def test_voicemail_unchanged_when_feature_off(app):
    upsert_contact("+15551112222", "Mom")
    set_setting("voicemail_prompt", "Please leave a message.")
    assert format_voicemail_prompt("+15551112222") == "Please leave a message."
