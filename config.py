import os
from datetime import timedelta

from dotenv import load_dotenv

load_dotenv()


def require_env(key):
    value = os.getenv(key)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {key}")
    return value


def _positive_int_env(key, default):
    """Read a positive integer env var, falling back to ``default`` when unset or invalid."""
    raw = os.getenv(key)
    if raw is None:
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    return value if value > 0 else default


class Config:
    TWILIO_ACCOUNT_SID = require_env("TWILIO_ACCOUNT_SID")
    TWILIO_AUTH_TOKEN = require_env("TWILIO_AUTH_TOKEN")
    TWILIO_PHONE_NUMBER = require_env("TWILIO_PHONE_NUMBER")

    BASE_URL = require_env("BASE_URL").rstrip("/")

    DATA_DIR = os.getenv("DATA_DIR", os.path.join(os.path.dirname(__file__), "data"))
    RECORDINGS_DIR = os.path.join(DATA_DIR, "recordings")

    SECRET_KEY = os.getenv("FLASK_SECRET_KEY", "dev-secret-change-me")

    # Admin UI credentials. ADMIN_PASSWORD_HASH (werkzeug hash) takes precedence
    # over the plaintext ADMIN_PASSWORD when both are present.
    ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin")
    ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD")
    ADMIN_PASSWORD_HASH = os.getenv("ADMIN_PASSWORD_HASH")

    # Session cookie hardening. Secure cookies require HTTPS, which is how the app
    # is reached in production (through NPM). Fall back to non-secure for local
    # http development so the session still works.
    SESSION_COOKIE_SECURE = BASE_URL.lower().startswith("https://")
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"

    # Session lifetime is bounded two ways: an idle timeout that logs out inactive
    # sessions, and an absolute cap from login time so an active session cannot be
    # extended indefinitely. Both are configurable via environment variables.
    SESSION_IDLE_TIMEOUT = timedelta(minutes=_positive_int_env("SESSION_IDLE_TIMEOUT_MINUTES", 30))
    SESSION_ABSOLUTE_MAX = timedelta(hours=_positive_int_env("SESSION_ABSOLUTE_MAX_HOURS", 8))

    # The signed cookie should live no longer than the absolute session cap.
    PERMANENT_SESSION_LIFETIME = SESSION_ABSOLUTE_MAX
