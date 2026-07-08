"""Session-based authentication for the admin UI.

A single admin account is configured via environment variables. The password is
verified against ``ADMIN_PASSWORD_HASH`` (a werkzeug hash) when present, or a
plaintext ``ADMIN_PASSWORD`` otherwise. Credentials never touch the database.
"""

import hmac
import logging
import time
from functools import wraps

from flask import redirect, request, session, url_for
from werkzeug.security import check_password_hash

from config import Config

logger = logging.getLogger(__name__)

SESSION_KEY = "admin_logged_in"
LOGIN_AT_KEY = "_login_at"
LAST_ACTIVITY_KEY = "_last_activity"


def verify_credentials(username, password):
    """Return True only if the supplied credentials match the configured admin.

    Uses constant-time comparisons to avoid leaking timing information about the
    username or a plaintext password.
    """
    if not username or password is None:
        return False

    username_ok = hmac.compare_digest(str(username), str(Config.ADMIN_USERNAME))

    if Config.ADMIN_PASSWORD_HASH:
        password_ok = check_password_hash(Config.ADMIN_PASSWORD_HASH, password)
    elif Config.ADMIN_PASSWORD:
        password_ok = hmac.compare_digest(str(password), str(Config.ADMIN_PASSWORD))
    else:
        logger.error(
            "No ADMIN_PASSWORD or ADMIN_PASSWORD_HASH configured; admin login "
            "is disabled."
        )
        return False

    # Evaluate both sides regardless of the username result to keep timing flat.
    return username_ok and password_ok


def login_user(username):
    # Clear any pre-existing session data to regenerate the session and avoid
    # session fixation, then establish the authenticated session.
    session.clear()
    now = time.time()
    session[SESSION_KEY] = True
    session["admin_username"] = username
    session[LOGIN_AT_KEY] = now
    session[LAST_ACTIVITY_KEY] = now
    session.permanent = True


def logout_user():
    session.clear()


def _session_expired():
    """Return True if the current session has passed its idle or absolute limit.

    Sessions missing the login/activity timestamps (e.g. created before these
    limits existed) are treated as expired so they are forced to re-authenticate.
    """
    now = time.time()

    login_at = session.get(LOGIN_AT_KEY)
    if login_at is None:
        return True
    if now - login_at > Config.SESSION_ABSOLUTE_MAX.total_seconds():
        return True

    last_activity = session.get(LAST_ACTIVITY_KEY)
    if last_activity is None:
        return True
    if now - last_activity > Config.SESSION_IDLE_TIMEOUT.total_seconds():
        return True

    return False


def is_logged_in():
    if not session.get(SESSION_KEY):
        return False

    if _session_expired():
        logout_user()
        return False

    session[LAST_ACTIVITY_KEY] = time.time()
    return True


def login_required(view):
    """Redirect unauthenticated requests to the login page with a safe next param."""

    @wraps(view)
    def wrapped(*args, **kwargs):
        if not is_logged_in():
            return redirect(url_for("admin.login", next=request.full_path.rstrip("?")))
        return view(*args, **kwargs)

    return wrapped
