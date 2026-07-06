"""Session-based authentication for the admin UI.

A single admin account is configured via environment variables. The password is
verified against ``ADMIN_PASSWORD_HASH`` (a werkzeug hash) when present, or a
plaintext ``ADMIN_PASSWORD`` otherwise. Credentials never touch the database.
"""

import hmac
import logging
from functools import wraps

from flask import redirect, request, session, url_for
from werkzeug.security import check_password_hash

from config import Config

logger = logging.getLogger(__name__)

SESSION_KEY = "admin_logged_in"


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
    session[SESSION_KEY] = True
    session["admin_username"] = username
    session.permanent = True


def logout_user():
    session.pop(SESSION_KEY, None)
    session.pop("admin_username", None)


def is_logged_in():
    return bool(session.get(SESSION_KEY))


def login_required(view):
    """Redirect unauthenticated requests to the login page with a safe next param."""

    @wraps(view)
    def wrapped(*args, **kwargs):
        if not is_logged_in():
            return redirect(url_for("admin.login", next=request.full_path.rstrip("?")))
        return view(*args, **kwargs)

    return wrapped
