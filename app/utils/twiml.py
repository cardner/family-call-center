from twilio.twiml.voice_response import VoiceResponse

from app.utils.greeting import format_menu_greeting
from app.utils.settings import get_block_action, get_setting
from app.utils.ssml import apply_ssml_to_say
from app.utils.voices import ivr_voice_language, normalize_ivr_voice
from config import Config


def get_ivr_voice():
    """Return the configured Twilio neural voice id."""
    return normalize_ivr_voice(get_setting("ivr_voice"))


def say_prompt(parent, text):
    """Speak IVR text with the configured neural voice and SSML support."""
    voice = get_ivr_voice()
    say = parent.say(voice=voice, language=ivr_voice_language(voice))
    apply_ssml_to_say(say, text)


def twiml_response(vr):
    """Return a Flask response with correct Content-Type for TwiML."""
    from flask import Response

    return Response(str(vr), mimetype="text/xml")


def error_response(message="Sorry, something went wrong. Please try again."):
    """Return a friendly TwiML error that redirects back to the main menu."""
    vr = VoiceResponse()
    say_prompt(vr, message)
    vr.redirect(f"{Config.BASE_URL}/call")
    return twiml_response(vr)


def blocked_caller_twiml():
    """Build the TwiML response for a blocked caller.

    ``reject`` gives a busy signal with no audio; ``message`` plays the
    configured prompt and hangs up. Either way the caller never reaches the menu
    or voicemail.
    """
    vr = VoiceResponse()
    if get_block_action() == "message":
        say_prompt(vr, get_setting("blocked_caller_message"))
        vr.hangup()
    else:
        vr.reject(reason="busy")
    return twiml_response(vr)


def main_menu_twiml(caller_id=None):
    """Build and return the main menu TwiML using the configured greeting.

    The greeting is the configurable intro followed by one "press N" option per
    enabled voicemail box, personalized with the caller's contact name when the
    feature is enabled. SSML tags are rendered via the Twilio SDK.
    """
    vr = VoiceResponse()
    gather = vr.gather(
        num_digits=1, action=f"{Config.BASE_URL}/call/route", method="POST", timeout=10
    )
    say_prompt(gather, format_menu_greeting(caller_id))
    # If no input, repeat the menu
    vr.redirect(f"{Config.BASE_URL}/call")
    return twiml_response(vr)
