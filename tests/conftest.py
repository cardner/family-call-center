"""Shared pytest fixtures.

Environment variables are set here, before any application module is imported,
so that config.py (which reads them at import time) picks up test values and a
temporary data directory.
"""

import os
import tempfile

# --- Test environment (must be set before importing the app) ---------------
_TMP_DATA_DIR = tempfile.mkdtemp(prefix="fcc-test-")

os.environ.setdefault("TWILIO_ACCOUNT_SID", "AC" + "0" * 32)
os.environ.setdefault("TWILIO_AUTH_TOKEN", "test_auth_token")
os.environ.setdefault("TWILIO_PHONE_NUMBER", "+15550001111")
os.environ.setdefault("BASE_URL", "https://voicemail.test")
os.environ["DATA_DIR"] = _TMP_DATA_DIR
os.environ.setdefault("FLASK_SECRET_KEY", "test-secret-key")
os.environ.setdefault("ADMIN_USERNAME", "admin")
os.environ.setdefault("ADMIN_PASSWORD", "s3cret-pass")

import pytest  # noqa: E402
from twilio.request_validator import RequestValidator  # noqa: E402

from app import create_app  # noqa: E402
from app.utils.db import get_connection, init_db, log_recording  # noqa: E402
from app.utils.settings import DEFAULT_SETTINGS  # noqa: E402
from config import Config  # noqa: E402
from tests.fixtures.sample_audio import WAV_BYTES  # noqa: E402


def _reset_db():
    init_db()
    with get_connection() as conn:
        conn.execute("DELETE FROM recordings")
        conn.execute("DELETE FROM settings")
        conn.execute("DELETE FROM contacts")
        conn.execute("DELETE FROM blocked_numbers")
        conn.execute("DELETE FROM voicemail_boxes")
        conn.commit()
    # Re-seed default settings and the four voicemail boxes after wiping.
    from app.utils.boxes import seed_default_boxes
    from app.utils.settings import seed_default_settings

    seed_default_settings()
    seed_default_boxes()


def _make_app(csrf_enabled=False, ratelimit_enabled=False):
    app = create_app()
    app.config.update(
        TESTING=True,
        WTF_CSRF_ENABLED=csrf_enabled,
        RATELIMIT_ENABLED=ratelimit_enabled,
        # Allow the test client (http) to persist the session cookie.
        SESSION_COOKIE_SECURE=False,
    )
    return app


@pytest.fixture(autouse=True)
def clean_db():
    """Isolate each test with a fresh recordings table and default settings."""
    _reset_db()
    yield


@pytest.fixture
def app():
    return _make_app()


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def auth_client(app):
    """A test client with an authenticated admin session."""
    import time

    client = app.test_client()
    now = time.time()
    with client.session_transaction() as sess:
        sess["admin_logged_in"] = True
        sess["admin_username"] = Config.ADMIN_USERNAME
        sess["_login_at"] = now
        sess["_last_activity"] = now
    return client


@pytest.fixture
def make_app():
    """Factory so individual tests can enable CSRF or rate limiting."""
    return _make_app


@pytest.fixture
def sample_recording():
    """Insert a recording row and write its WAV file. Returns metadata dict."""

    def _create(
        caller_id="+15551234567",
        subdir="2026/07/05",
        name="msg.wav",
        transcript=None,
        transcript_status="disabled",
        read_at=None,
        twilio_sid=None,
    ):
        rel_path = os.path.join(subdir, name)
        abs_dir = os.path.join(Config.RECORDINGS_DIR, subdir)
        os.makedirs(abs_dir, exist_ok=True)
        abs_path = os.path.join(abs_dir, name)
        with open(abs_path, "wb") as handle:
            handle.write(WAV_BYTES)

        recording_id = log_recording(
            created_at="2026-07-05T12:00:00+00:00",
            caller_id=caller_id,
            duration=12,
            filename=rel_path,
            file_size=len(WAV_BYTES),
            twilio_sid=twilio_sid or ("RE" + "a" * 32),
            transcript_status=transcript_status,
        )
        if transcript is not None or read_at is not None:
            with get_connection() as conn:
                conn.execute(
                    "UPDATE recordings SET transcript = ?, read_at = ? WHERE id = ?",
                    (transcript, read_at, recording_id),
                )
                conn.commit()
        return {
            "id": recording_id,
            "filename": rel_path,
            "abs_path": abs_path,
            "caller_id": caller_id,
        }

    return _create


@pytest.fixture
def twilio_post():
    """Return a helper that POSTs a Twilio-signed request via the test client."""

    def _post(client, path, data=None):
        data = data or {}
        url = Config.BASE_URL + path
        validator = RequestValidator(Config.TWILIO_AUTH_TOKEN)
        signature = validator.compute_signature(url, data)
        return client.post(
            path,
            data=data,
            headers={"X-Twilio-Signature": signature},
        )

    return _post
