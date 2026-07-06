import logging
import math
import os
from datetime import datetime, timezone

from flask import (
    Blueprint,
    abort,
    flash,
    redirect,
    render_template,
    request,
    send_file,
    session,
    url_for,
)

from app.extensions import limiter
from app.forms.admin_forms import (
    ConnectionTestForm,
    DeleteMessageForm,
    LoginForm,
    LogoutForm,
    SettingsForm,
)
from app.utils.auth import login_required, login_user, logout_user, verify_credentials
from app.utils.connection_test import run_all_checks, webhook_urls
from app.utils.db import (
    count_recordings,
    delete_recording,
    get_recording,
    list_recordings,
)
from app.utils.settings import get_all_settings, set_setting
from app.utils.validation import clamp_int, sanitize_ivr_text, sanitize_text, safe_next_url
from config import Config

logger = logging.getLogger(__name__)
admin_bp = Blueprint("admin", __name__, url_prefix="/admin")

_LOGIN_ONLY_POST = lambda: request.method != "POST"


@admin_bp.get("/login")
@admin_bp.post("/login")
@limiter.limit("5 per minute", exempt_when=_LOGIN_ONLY_POST)
def login():
    form = LoginForm()
    next_url = safe_next_url(request.args.get("next") or request.form.get("next"))

    if form.validate_on_submit():
        if verify_credentials(form.username.data, form.password.data):
            login_user(form.username.data)
            logger.info("Admin login succeeded for %s", form.username.data)
            return redirect(next_url or url_for("admin.dashboard"))
        logger.warning("Failed admin login attempt from %s", request.remote_addr)
        flash("Invalid credentials.", "error")

    return render_template("admin/login.html", form=form, next_url=next_url)


@admin_bp.post("/logout")
def logout():
    form = LogoutForm()
    if form.validate_on_submit():
        logout_user()
        flash("You have been logged out.", "success")
    return redirect(url_for("admin.login"))


@admin_bp.get("/")
@login_required
def dashboard():
    total = count_recordings()
    recent = list_recordings(limit=5, offset=0)
    connection_summary = session.get("connection_summary")
    return render_template(
        "admin/index.html",
        total=total,
        recent=recent,
        connection_summary=connection_summary,
        logout_form=LogoutForm(),
    )


@admin_bp.get("/messages")
@login_required
def messages():
    page = clamp_int(request.args.get("page"), default=1, min_value=1, max_value=100000)
    per_page = clamp_int(
        request.args.get("per_page"), default=20, min_value=1, max_value=100
    )
    query = sanitize_text(request.args.get("q", ""), max_length=32) or None

    total = count_recordings(caller_filter=query)
    total_pages = max(1, math.ceil(total / per_page)) if total else 1
    if page > total_pages:
        page = total_pages
    offset = (page - 1) * per_page

    rows = list_recordings(limit=per_page, offset=offset, caller_filter=query)

    return render_template(
        "admin/messages.html",
        recordings=rows,
        page=page,
        per_page=per_page,
        total=total,
        total_pages=total_pages,
        query=query or "",
        logout_form=LogoutForm(),
    )


@admin_bp.get("/messages/<int:message_id>")
@login_required
def message_detail(message_id):
    row = get_recording(message_id)
    if row is None:
        abort(404)
    return render_template(
        "admin/message_detail.html",
        recording=row,
        delete_form=DeleteMessageForm(),
        logout_form=LogoutForm(),
    )


@admin_bp.get("/messages/<int:message_id>/audio")
@login_required
def message_audio(message_id):
    row = get_recording(message_id)
    if row is None:
        abort(404)

    filename = row["filename"] or ""
    recordings_root = os.path.realpath(Config.RECORDINGS_DIR)
    target = os.path.realpath(os.path.join(recordings_root, filename))

    # Path must resolve inside the recordings directory (no traversal).
    if not target.startswith(recordings_root + os.sep):
        logger.warning("Blocked audio path traversal attempt: %r", filename)
        abort(404)
    if not os.path.isfile(target):
        abort(404)

    return send_file(target, mimetype="audio/wav", conditional=True)


@admin_bp.post("/messages/<int:message_id>/delete")
@login_required
def message_delete(message_id):
    form = DeleteMessageForm()
    if not form.validate_on_submit():
        abort(400)

    if delete_recording(message_id):
        flash("Message deleted.", "success")
    else:
        flash("Message not found.", "error")
    return redirect(url_for("admin.messages"))


@admin_bp.route("/settings", methods=["GET", "POST"])
@login_required
def settings():
    form = SettingsForm()

    if form.validate_on_submit():
        set_setting("greeting", sanitize_ivr_text(form.greeting.data))
        set_setting(
            "invalid_digit_message", sanitize_ivr_text(form.invalid_digit_message.data)
        )
        set_setting("voicemail_prompt", sanitize_ivr_text(form.voicemail_prompt.data))
        set_setting("voicemail_thanks", sanitize_ivr_text(form.voicemail_thanks.data))
        set_setting("max_recording_seconds", str(form.max_recording_seconds.data))
        flash("Settings saved.", "success")
        return redirect(url_for("admin.settings"))

    if request.method == "GET":
        current = get_all_settings()
        form.greeting.data = current.get("greeting")
        form.invalid_digit_message.data = current.get("invalid_digit_message")
        form.voicemail_prompt.data = current.get("voicemail_prompt")
        form.voicemail_thanks.data = current.get("voicemail_thanks")
        try:
            form.max_recording_seconds.data = int(current.get("max_recording_seconds"))
        except (TypeError, ValueError):
            form.max_recording_seconds.data = 300

    return render_template(
        "admin/settings.html", form=form, logout_form=LogoutForm()
    )


@admin_bp.get("/connection")
@login_required
def connection():
    return render_template(
        "admin/connection.html",
        results=None,
        webhook_urls=webhook_urls(),
        form=ConnectionTestForm(),
        phone_number=Config.TWILIO_PHONE_NUMBER,
        logout_form=LogoutForm(),
    )


@admin_bp.post("/connection/test")
@login_required
@limiter.limit("3 per minute")
def connection_test():
    form = ConnectionTestForm()
    if not form.validate_on_submit():
        abort(400)

    results = run_all_checks()
    session["connection_summary"] = {
        "overall": results["overall"],
        "tested_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
    }

    return render_template(
        "admin/connection.html",
        results=results,
        webhook_urls=results["webhook_urls"],
        form=form,
        phone_number=Config.TWILIO_PHONE_NUMBER,
        logout_form=LogoutForm(),
    )
