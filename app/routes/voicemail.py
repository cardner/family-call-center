import logging
import os
import re
from datetime import datetime, timezone
from urllib.parse import urlparse

import requests as http_requests
from flask import Blueprint, request
from twilio.rest import Client
from twilio.twiml.voice_response import VoiceResponse

from app.utils.db import init_db, log_recording
from app.utils.settings import get_max_recording_seconds, get_setting
from app.utils.twilio_validator import validate_twilio_request
from app.utils.twiml import error_response, twiml_response
from app.utils.validation import parse_positive_int, sanitize_text
from config import Config

logger = logging.getLogger(__name__)
voicemail_bp = Blueprint("voicemail", __name__)

init_db()

# Twilio recording SIDs look like RE followed by 32 hex chars.
_RECORDING_SID_RE = re.compile(r"^RE[0-9a-fA-F]{32}$")


def _is_twilio_recording_url(url):
    """Only allow downloads from Twilio-owned HTTPS hosts."""
    try:
        parsed = urlparse(url)
    except (ValueError, TypeError):
        return False
    if parsed.scheme != "https":
        return False
    host = parsed.hostname or ""
    return host == "twilio.com" or host.endswith(".twilio.com")


@voicemail_bp.post("/voicemail")
@validate_twilio_request
def voicemail():
    """Prompt the caller to leave a message and start recording."""
    try:
        vr = VoiceResponse()
        vr.say(get_setting("voicemail_prompt"))
        vr.record(
            action=f"{Config.BASE_URL}/voicemail/done",
            recording_status_callback=f"{Config.BASE_URL}/voicemail/callback",
            recording_status_callback_method="POST",
            finish_on_key="#",
            max_length=get_max_recording_seconds(),
            play_beep=True,
        )
        return twiml_response(vr)
    except Exception:
        logger.exception("Error in /voicemail")
        return error_response()


@voicemail_bp.post("/voicemail/done")
@validate_twilio_request
def voicemail_done():
    """Thank the caller and end the call after recording."""
    try:
        vr = VoiceResponse()
        vr.say(get_setting("voicemail_thanks"))
        vr.hangup()
        return twiml_response(vr)
    except Exception:
        logger.exception("Error in /voicemail/done")
        return error_response()


@voicemail_bp.post("/voicemail/callback")
@validate_twilio_request
def voicemail_callback():
    """
    Called by Twilio when a recording is complete.
    Downloads the audio, saves it locally, logs metadata, then deletes from Twilio.

    Even though the request signature is verified, every field is still treated
    as untrusted and validated before use.
    """
    recording_sid = request.form.get("RecordingSid", "")
    recording_url = request.form.get("RecordingUrl", "")
    caller_id = sanitize_text(request.form.get("From", "unknown"), max_length=32)
    duration = parse_positive_int(
        request.form.get("RecordingDuration", "0"),
        min_value=0,
        max_value=600,
        default=None,
    )

    if not _RECORDING_SID_RE.match(recording_sid):
        logger.warning("Rejected callback: invalid RecordingSid %r", recording_sid)
        return ("", 400)
    if not _is_twilio_recording_url(recording_url):
        logger.warning("Rejected callback: non-Twilio RecordingUrl %r", recording_url)
        return ("", 400)
    if duration is None:
        logger.warning("Rejected callback: invalid RecordingDuration")
        return ("", 400)

    try:
        logger.info(
            "Recording complete: sid=%s duration=%s from=%s",
            recording_sid,
            duration,
            caller_id,
        )

        now = datetime.now(timezone.utc)
        date_path = now.strftime("%Y/%m/%d")
        timestamp = now.strftime("%Y-%m-%d_%H-%M-%S")
        filename = f"{timestamp}_{recording_sid}.wav"

        save_dir = os.path.join(Config.RECORDINGS_DIR, date_path)
        os.makedirs(save_dir, exist_ok=True)
        filepath = os.path.join(save_dir, filename)

        # Download the recording from Twilio (mp3 -> wav via URL param)
        audio_url = f"{recording_url}.wav"
        response = http_requests.get(
            audio_url,
            auth=(Config.TWILIO_ACCOUNT_SID, Config.TWILIO_AUTH_TOKEN),
            timeout=30,
        )
        response.raise_for_status()

        with open(filepath, "wb") as f:
            f.write(response.content)

        file_size = os.path.getsize(filepath)
        logger.info("Saved recording to %s (%d bytes)", filepath, file_size)

        log_recording(
            created_at=now.isoformat(),
            caller_id=caller_id,
            duration=duration,
            filename=os.path.join(date_path, filename),
            file_size=file_size,
            twilio_sid=recording_sid,
        )

        # Delete from Twilio to avoid storage costs
        _delete_from_twilio(recording_sid)

        return ("", 204)
    except Exception:
        logger.exception("Error in /voicemail/callback for sid=%s", recording_sid)
        return ("", 500)


def _delete_from_twilio(recording_sid):
    """Delete a recording from Twilio's servers."""
    try:
        client = Client(Config.TWILIO_ACCOUNT_SID, Config.TWILIO_AUTH_TOKEN)
        client.recordings(recording_sid).delete()
        logger.info("Deleted recording %s from Twilio", recording_sid)
    except Exception:
        logger.warning(
            "Could not delete recording %s from Twilio", recording_sid, exc_info=True
        )
