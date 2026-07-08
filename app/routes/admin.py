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
    BlockCallerForm,
    BlockedNumberForm,
    BoxForm,
    ConnectionTestForm,
    ContactForm,
    ContactsImportForm,
    DeleteBlockedForm,
    DeleteContactForm,
    DeleteMessageForm,
    ImportBlocklistForm,
    LoginForm,
    LogoutForm,
    MarkAllReadForm,
    NotificationTestForm,
    SettingsForm,
)
from app.utils.auth import login_required, login_user, logout_user, verify_credentials
from app.utils.boxes import get_box, get_box_by_slug, list_boxes, update_box
from app.utils.blocklist_import import (
    SEED_SOURCE,
    BlocklistImportError,
    import_callshield_seed,
)
from app.utils.call_policy import is_blocked, normalize_caller_id
from app.utils.connection_test import run_all_checks, webhook_urls
from app.utils.contacts import parse_contacts_csv
from app.utils.db import (
    bulk_upsert_contacts,
    count_blocked,
    count_blocked_by_source,
    count_contacts,
    count_recordings,
    count_unread_recordings,
    delete_blocked,
    delete_blocked_by_source,
    delete_contact,
    delete_recording,
    get_blocked,
    get_contact,
    get_recording,
    list_blocked,
    list_contacts,
    list_recordings,
    mark_all_recordings_read,
    mark_recording_read,
    upsert_blocked,
    upsert_contact,
)
from app.utils.notify import notification_summary, send_test_notification
from app.utils.settings import get_all_settings, parse_phone_numbers, set_setting
from app.utils.validation import clamp_int, sanitize_ivr_text, sanitize_text, safe_next_url
from app.utils.voices import ivr_voice_meta, normalize_ivr_voice
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
        flash("You have been logged out.", "success")
    # Always end the session on a logout POST, even if CSRF validation fails, so
    # a stale or forged token can never leave an admin logged in.
    logout_user()
    return redirect(url_for("admin.login"))


@admin_bp.get("/")
@login_required
def dashboard():
    total = count_recordings()
    unread = count_unread_recordings()
    recent = list_recordings(limit=5, offset=0)
    connection_summary = session.get("connection_summary")
    return render_template(
        "admin/index.html",
        total=total,
        unread=unread,
        recent=recent,
        connection_summary=connection_summary,
        notifications=notification_summary(),
        logout_form=LogoutForm(),
    )


@admin_bp.get("/messages")
@login_required
def messages():
    page = clamp_int(request.args.get("page"), default=1, min_value=1, max_value=100000)
    per_page = clamp_int(
        request.args.get("per_page"), default=20, min_value=1, max_value=100
    )
    query = sanitize_text(request.args.get("q", ""), max_length=64) or None
    unread_only = request.args.get("unread") == "1"

    boxes = list_boxes()
    box_slug = sanitize_text(request.args.get("box", ""), max_length=32) or None
    selected_box = get_box_by_slug(box_slug) if box_slug else None
    box_id = selected_box["id"] if selected_box else None

    total = count_recordings(search=query, unread_only=unread_only, box_id=box_id)
    total_pages = max(1, math.ceil(total / per_page)) if total else 1
    if page > total_pages:
        page = total_pages
    offset = (page - 1) * per_page

    rows = list_recordings(
        limit=per_page,
        offset=offset,
        search=query,
        unread_only=unread_only,
        box_id=box_id,
    )

    return render_template(
        "admin/messages.html",
        recordings=rows,
        page=page,
        per_page=per_page,
        total=total,
        total_pages=total_pages,
        query=query or "",
        unread_only=unread_only,
        boxes=boxes,
        box_filter=selected_box["slug"] if selected_box else "",
        mark_all_read_form=MarkAllReadForm(),
        logout_form=LogoutForm(),
    )


@admin_bp.post("/messages/mark-all-read")
@login_required
def messages_mark_all_read():
    form = MarkAllReadForm()
    if not form.validate_on_submit():
        abort(400)

    updated = mark_all_recordings_read()
    if updated:
        flash(f"Marked {updated} message(s) as read.", "success")
    else:
        flash("No unread messages.", "success")
    return redirect(url_for("admin.messages"))


@admin_bp.get("/messages/<int:message_id>")
@login_required
def message_detail(message_id):
    row = get_recording(message_id)
    if row is None:
        abort(404)
    # Opening a message marks it read.
    mark_recording_read(message_id)
    box = get_box(row["box_id"]) if row["box_id"] else None
    return render_template(
        "admin/message_detail.html",
        recording=row,
        box=box,
        delete_form=DeleteMessageForm(),
        block_form=BlockCallerForm(),
        caller_blocked=is_blocked(row["caller_id"]),
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
        set_setting("ivr_voice", normalize_ivr_voice(form.ivr_voice.data))
        set_setting("max_recording_seconds", str(form.max_recording_seconds.data))
        set_setting(
            "notify_phone_numbers",
            ",".join(parse_phone_numbers(form.notify_phone_numbers.data)),
        )
        set_setting(
            "transcription_enabled",
            "true" if form.transcription_enabled.data else "false",
        )
        set_setting(
            "personalized_greeting_enabled",
            "true" if form.personalized_greeting_enabled.data else "false",
        )
        set_setting("block_action", form.block_action.data)
        set_setting(
            "blocked_caller_message",
            sanitize_ivr_text(form.blocked_caller_message.data or ""),
        )
        flash("Settings saved.", "success")
        return redirect(url_for("admin.settings"))

    if request.method == "GET":
        current = get_all_settings()
        form.greeting.data = current.get("greeting")
        form.invalid_digit_message.data = current.get("invalid_digit_message")
        form.voicemail_prompt.data = current.get("voicemail_prompt")
        form.voicemail_thanks.data = current.get("voicemail_thanks")
        form.ivr_voice.data = normalize_ivr_voice(current.get("ivr_voice"))
        try:
            form.max_recording_seconds.data = int(current.get("max_recording_seconds"))
        except (TypeError, ValueError):
            form.max_recording_seconds.data = 300
        form.notify_phone_numbers.data = "\n".join(
            parse_phone_numbers(current.get("notify_phone_numbers"))
        )
        form.transcription_enabled.data = current.get("transcription_enabled") == "true"
        form.personalized_greeting_enabled.data = (
            current.get("personalized_greeting_enabled") == "true"
        )
        form.block_action.data = current.get("block_action")
        form.blocked_caller_message.data = current.get("blocked_caller_message")

    return render_template(
        "admin/settings.html",
        form=form,
        logout_form=LogoutForm(),
        ivr_voice_meta=ivr_voice_meta(),
    )


@admin_bp.get("/boxes")
@login_required
def boxes():
    return render_template(
        "admin/boxes.html",
        boxes=list_boxes(),
        logout_form=LogoutForm(),
    )


@admin_bp.route("/boxes/<int:box_id>/edit", methods=["GET", "POST"])
@login_required
def box_edit(box_id):
    row = get_box(box_id)
    if row is None:
        abort(404)

    form = BoxForm()
    if form.validate_on_submit():
        digit = form.extension_digit.data
        # Menu digits must be unique so a keypress maps to exactly one box.
        clash = next(
            (
                b
                for b in list_boxes()
                if b["extension_digit"] == digit and b["id"] != box_id
            ),
            None,
        )
        if clash is not None:
            flash(
                f"Digit {digit} is already used by {clash['display_name']}.", "error"
            )
        else:
            update_box(
                box_id,
                display_name=sanitize_text(form.display_name.data, 120),
                extension_digit=digit,
                voicemail_prompt=sanitize_ivr_text(form.voicemail_prompt.data or ""),
                voicemail_thanks=sanitize_ivr_text(form.voicemail_thanks.data or ""),
                notify_phone_numbers=",".join(
                    parse_phone_numbers(form.notify_phone_numbers.data)
                ),
                enabled=1 if form.enabled.data else 0,
            )
            flash("Voicemail box saved.", "success")
            return redirect(url_for("admin.boxes"))

    if request.method == "GET":
        form.display_name.data = row["display_name"]
        form.extension_digit.data = row["extension_digit"]
        form.voicemail_prompt.data = row["voicemail_prompt"]
        form.voicemail_thanks.data = row["voicemail_thanks"]
        form.notify_phone_numbers.data = "\n".join(
            parse_phone_numbers(row["notify_phone_numbers"])
        )
        form.enabled.data = bool(row["enabled"])

    return render_template(
        "admin/box_form.html",
        form=form,
        box=row,
        logout_form=LogoutForm(),
    )


@admin_bp.get("/connection")
@login_required
def connection():
    return render_template(
        "admin/connection.html",
        results=None,
        webhook_urls=webhook_urls(),
        form=ConnectionTestForm(),
        notification_form=NotificationTestForm(),
        notifications=notification_summary(),
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
        "tested_at": datetime.now(timezone.utc).isoformat(),
    }

    return render_template(
        "admin/connection.html",
        results=results,
        webhook_urls=results["webhook_urls"],
        form=form,
        notification_form=NotificationTestForm(),
        notifications=notification_summary(),
        phone_number=Config.TWILIO_PHONE_NUMBER,
        logout_form=LogoutForm(),
    )


@admin_bp.post("/connection/notify-test")
@login_required
@limiter.limit("3 per minute")
def notification_test():
    form = NotificationTestForm()
    if not form.validate_on_submit():
        abort(400)

    results = send_test_notification()
    if not results:
        flash("No SMS recipients configured. Add numbers on the Settings page.", "error")
    else:
        sent = sum(1 for r in results if r["status"] == "sent")
        failed = len(results) - sent
        if failed == 0:
            flash(f"Test SMS sent to {sent} recipient(s).", "success")
        else:
            flash(
                f"Test SMS sent to {sent} recipient(s); {failed} failed. "
                "Check the logs for details.",
                "error",
            )

    return redirect(url_for("admin.connection"))


@admin_bp.get("/contacts")
@login_required
def contacts():
    page = clamp_int(request.args.get("page"), default=1, min_value=1, max_value=100000)
    per_page = clamp_int(
        request.args.get("per_page"), default=50, min_value=1, max_value=100
    )
    total = count_contacts()
    total_pages = max(1, math.ceil(total / per_page)) if total else 1
    if page > total_pages:
        page = total_pages
    offset = (page - 1) * per_page

    rows = list_contacts(limit=per_page, offset=offset)

    return render_template(
        "admin/contacts.html",
        contacts=rows,
        page=page,
        per_page=per_page,
        total=total,
        total_pages=total_pages,
        delete_form=DeleteContactForm(),
        import_form=ContactsImportForm(),
        logout_form=LogoutForm(),
    )


@admin_bp.route("/contacts/new", methods=["GET", "POST"])
@login_required
def contact_new():
    form = ContactForm()
    if form.validate_on_submit():
        # validate_phone stored the normalized number back on the field.
        upsert_contact(
            form.phone.data,
            sanitize_text(form.display_name.data, 120),
            is_vip=form.is_vip.data,
        )
        flash("Contact saved.", "success")
        return redirect(url_for("admin.contacts"))

    return render_template(
        "admin/contact_form.html",
        form=form,
        heading="Add contact",
        logout_form=LogoutForm(),
    )


@admin_bp.route("/contacts/<int:contact_id>/edit", methods=["GET", "POST"])
@login_required
def contact_edit(contact_id):
    row = get_contact(contact_id)
    if row is None:
        abort(404)

    form = ContactForm()
    if form.validate_on_submit():
        upsert_contact(
            form.phone.data,
            sanitize_text(form.display_name.data, 120),
            is_vip=form.is_vip.data,
        )
        flash("Contact saved.", "success")
        return redirect(url_for("admin.contacts"))

    if request.method == "GET":
        form.phone.data = row["phone"]
        form.display_name.data = row["display_name"]
        form.is_vip.data = bool(row["is_vip"])

    return render_template(
        "admin/contact_form.html",
        form=form,
        heading="Edit contact",
        logout_form=LogoutForm(),
    )


@admin_bp.post("/contacts/<int:contact_id>/delete")
@login_required
def contact_delete(contact_id):
    form = DeleteContactForm()
    if not form.validate_on_submit():
        abort(400)

    if delete_contact(contact_id):
        flash("Contact deleted.", "success")
    else:
        flash("Contact not found.", "error")
    return redirect(url_for("admin.contacts"))


@admin_bp.post("/contacts/import")
@login_required
def contacts_import():
    form = ContactsImportForm()
    if not form.validate_on_submit():
        flash("Please upload a valid .csv file.", "error")
        return redirect(url_for("admin.contacts"))

    raw = form.file.data.read()
    try:
        text = raw.decode("utf-8-sig")
    except (UnicodeDecodeError, AttributeError):
        flash("Could not read the file. Save it as UTF-8 CSV and try again.", "error")
        return redirect(url_for("admin.contacts"))

    pairs, invalid = parse_contacts_csv(text)
    imported = bulk_upsert_contacts(pairs) if pairs else 0

    message = f"Imported {imported} contact(s)."
    if invalid:
        message += f" Skipped {invalid} invalid row(s)."
    flash(message, "success" if imported else "error")
    return redirect(url_for("admin.contacts"))


@admin_bp.get("/blocked")
@login_required
def blocked():
    page = clamp_int(request.args.get("page"), default=1, min_value=1, max_value=100000)
    per_page = clamp_int(
        request.args.get("per_page"), default=50, min_value=1, max_value=100
    )
    total = count_blocked()
    total_pages = max(1, math.ceil(total / per_page)) if total else 1
    if page > total_pages:
        page = total_pages
    offset = (page - 1) * per_page

    rows = list_blocked(limit=per_page, offset=offset)

    return render_template(
        "admin/blocked.html",
        blocked=rows,
        page=page,
        per_page=per_page,
        total=total,
        seed_count=count_blocked_by_source(SEED_SOURCE),
        delete_form=DeleteBlockedForm(),
        import_form=ImportBlocklistForm(),
        total_pages=total_pages,
        logout_form=LogoutForm(),
    )


@admin_bp.route("/blocked/new", methods=["GET", "POST"])
@login_required
def blocked_new():
    form = BlockedNumberForm()
    if form.validate_on_submit():
        # validate_phone stored the normalized number back on the field.
        note = sanitize_text(form.note.data or "", 200) or None
        upsert_blocked(form.phone.data, note=note, source="user")
        flash("Number blocked.", "success")
        return redirect(url_for("admin.blocked"))

    return render_template(
        "admin/blocked_form.html",
        form=form,
        heading="Block a number",
        editing=False,
        logout_form=LogoutForm(),
    )


@admin_bp.route("/blocked/<int:blocked_id>/edit", methods=["GET", "POST"])
@login_required
def blocked_edit(blocked_id):
    row = get_blocked(blocked_id)
    if row is None:
        abort(404)

    form = BlockedNumberForm()
    if form.validate_on_submit():
        note = sanitize_text(form.note.data or "", 200) or None
        # The phone is fixed to the existing row; a manual edit takes ownership.
        upsert_blocked(row["phone"], note=note, source="user")
        flash("Blocked number updated.", "success")
        return redirect(url_for("admin.blocked"))

    if request.method == "GET":
        form.phone.data = row["phone"]
        form.note.data = row["note"]

    return render_template(
        "admin/blocked_form.html",
        form=form,
        heading="Edit blocked number",
        editing=True,
        logout_form=LogoutForm(),
    )


@admin_bp.post("/blocked/<int:blocked_id>/delete")
@login_required
def blocked_delete(blocked_id):
    form = DeleteBlockedForm()
    if not form.validate_on_submit():
        abort(400)

    if delete_blocked(blocked_id):
        flash("Number unblocked.", "success")
    else:
        flash("Blocked number not found.", "error")
    return redirect(url_for("admin.blocked"))


@admin_bp.post("/messages/<int:message_id>/block")
@login_required
def message_block(message_id):
    form = BlockCallerForm()
    if not form.validate_on_submit():
        abort(400)

    row = get_recording(message_id)
    if row is None:
        abort(404)

    phone = normalize_caller_id(row["caller_id"])
    if not phone:
        flash("This caller's number is unknown and cannot be blocked.", "error")
        return redirect(url_for("admin.message_detail", message_id=message_id))

    upsert_blocked(phone, note=f"Blocked from message #{message_id}", source="user")
    flash(f"Blocked {phone}.", "success")
    return redirect(url_for("admin.message_detail", message_id=message_id))


@admin_bp.post("/blocked/import-starter")
@login_required
@limiter.limit("3 per minute")
def blocked_import_starter():
    form = ImportBlocklistForm()
    if not form.validate_on_submit():
        abort(400)

    try:
        result = import_callshield_seed()
    except BlocklistImportError as exc:
        flash(str(exc), "error")
        return redirect(url_for("admin.blocked"))

    flash(
        f"Imported {result['added']} number(s) from the starter blocklist "
        f"({result['skipped']} already blocked).",
        "success",
    )
    return redirect(url_for("admin.blocked"))


@admin_bp.post("/blocked/remove-imported")
@login_required
def blocked_remove_imported():
    form = ImportBlocklistForm()
    if not form.validate_on_submit():
        abort(400)

    removed = delete_blocked_by_source(SEED_SOURCE)
    if removed:
        flash(f"Removed {removed} imported number(s).", "success")
    else:
        flash("No imported numbers to remove.", "success")
    return redirect(url_for("admin.blocked"))
