from twilio.twiml.voice_response import VoiceResponse

from app.utils.ssml import apply_ssml_to_say, normalize_ivr_ssml


def test_normalize_strips_unknown_tags():
    assert normalize_ivr_ssml("<b>Hi</b> there") == "Hi there"
    assert normalize_ivr_ssml("<script>x</script>Hello") == "xHello"


def test_normalize_keeps_allowed_ssml():
    raw = (
        'Welcome. <break time="300ms"/> '
        '<emphasis level="moderate">press 1</emphasis>.'
    )
    assert normalize_ivr_ssml(raw) == raw


def test_normalize_drops_invalid_break_time():
    assert normalize_ivr_ssml('Wait <break time="nope"/> now') == "Wait  now"


def test_apply_ssml_emits_unescaped_tags():
    vr = VoiceResponse()
    apply_ssml_to_say(
        vr.say(voice="Polly.Joanna-Neural", language="en-US"),
        '<emphasis level="moderate">press 1</emphasis>',
    )
    twiml = str(vr)
    assert "<emphasis level=\"moderate\">press 1</emphasis>" in twiml
    assert "&lt;emphasis" not in twiml


def test_apply_ssml_prosody_rate():
    vr = VoiceResponse()
    apply_ssml_to_say(
        vr.say(voice="Polly.Joanna-Neural", language="en-US"),
        '<prosody rate="slow">please wait</prosody>',
    )
    twiml = str(vr)
    assert '<prosody rate="slow">please wait</prosody>' in twiml
