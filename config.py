import os
from datetime import timedelta

from dotenv import load_dotenv

load_dotenv()


def require_env(key):
    value = os.getenv(key)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {key}")
    return value


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
    PERMANENT_SESSION_LIFETIME = timedelta(hours=24)
