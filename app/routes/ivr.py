import logging
import re

from flask import Blueprint, request
from twilio.twiml.voice_response import VoiceResponse

from app.utils.call_policy import is_blocked, should_skip_ivr_menu
from app.utils.settings import get_setting
from app.utils.twilio_validator import validate_twilio_request
from app.utils.twiml import (
    blocked_caller_twiml,
    error_response,
    main_menu_twiml,
    say_prompt,
    twiml_response,
)
from app.utils.validation import sanitize_text
from config import Config

logger = logging.getLogger(__name__)
ivr_bp = Blueprint("ivr", __name__)

_SINGLE_DIGIT_RE = re.compile(r"^[0-9]$")


@ivr_bp.post("/call")
@validate_twilio_request
def call():
    """Entry point for all incoming calls — presents the main menu.

    A VIP contact is always allowed through and skips the menu straight to
    voicemail (this wins over the blocklist). A blocked caller is otherwise
    rejected. Everyone else hears the main menu.
    """
    try:
        caller = sanitize_text(request.form.get("From", "unknown"), max_length=32)
        logger.info("Incoming call from %s", caller)

        if should_skip_ivr_menu(caller):
            logger.info("VIP caller %s skipping menu to voicemail", caller)
            vr = VoiceResponse()
            vr.redirect(f"{Config.BASE_URL}/voicemail")
            return twiml_response(vr)

        if is_blocked(caller):
            logger.info("Blocked call from %s", caller)
            return blocked_caller_twiml()

        return main_menu_twiml()
    except Exception:
        logger.exception("Error in /call")
        return error_response()


@ivr_bp.post("/call/route")
@validate_twilio_request
def route():
    """Routes keypad input from the main menu."""
    try:
        # Digits must be exactly one 0-9 character; anything else replays the menu.
        raw_digits = sanitize_text(request.form.get("Digits", ""), max_length=8)
        digit = raw_digits if _SINGLE_DIGIT_RE.match(raw_digits) else ""
        logger.info("Main menu digit pressed: %s", digit)

        vr = VoiceResponse()

        if digit == "1":
            vr.redirect(f"{Config.BASE_URL}/voicemail")
        else:
            say_prompt(vr, get_setting("invalid_digit_message"))
            vr.redirect(f"{Config.BASE_URL}/call")

        return twiml_response(vr)
    except Exception:
        logger.exception("Error in /call/route")
        return error_response()
