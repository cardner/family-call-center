import logging
import time

from flask import Flask, jsonify

from app.extensions import csrf, limiter
from config import Config

START_TIME = time.time()


def create_app():
    app = Flask(__name__)
    app.secret_key = Config.SECRET_KEY

    app.config.update(
        SESSION_COOKIE_SECURE=Config.SESSION_COOKIE_SECURE,
        SESSION_COOKIE_HTTPONLY=Config.SESSION_COOKIE_HTTPONLY,
        SESSION_COOKIE_SAMESITE=Config.SESSION_COOKIE_SAMESITE,
        PERMANENT_SESSION_LIFETIME=Config.PERMANENT_SESSION_LIFETIME,
        RATELIMIT_STORAGE_URI="memory://",
    )

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    csrf.init_app(app)
    limiter.init_app(app)

    from app.routes.admin import admin_bp
    from app.routes.ivr import ivr_bp
    from app.routes.voicemail import voicemail_bp

    app.register_blueprint(ivr_bp)
    app.register_blueprint(voicemail_bp)
    app.register_blueprint(admin_bp)

    # Twilio webhooks authenticate via request signature, not CSRF tokens, so the
    # webhook blueprints are exempt from CSRF protection.
    csrf.exempt(ivr_bp)
    csrf.exempt(voicemail_bp)

    @app.get("/health")
    def health():
        uptime_seconds = int(time.time() - START_TIME)
        return jsonify({"status": "ok", "uptime_seconds": uptime_seconds})

    return app
