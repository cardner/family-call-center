"""WTForms for the admin UI.

Every mutating admin request goes through one of these forms, giving us CSRF
protection (via Flask-WTF) and server-side validation in one place. Handlers
must not read ``request.form`` directly.
"""

from flask_wtf import FlaskForm
from flask_wtf.file import FileAllowed, FileField, FileRequired
from wtforms import (
    BooleanField,
    IntegerField,
    PasswordField,
    SelectField,
    SelectMultipleField,
    StringField,
    SubmitField,
    TextAreaField,
)
from wtforms.validators import DataRequired, Length, NumberRange, Optional, ValidationError

from app.utils.contacts import (
    CONTACT_NAME_MAX_LENGTH,
    EMAIL_MAX_LENGTH,
    is_valid_email,
)
from app.utils.phone import normalize_phone
from app.utils.settings import (
    BLOCK_ACTIONS,
    IVR_TEXT_MAX_LENGTH,
    MAX_RECORDING_SECONDS_MAX,
    MAX_RECORDING_SECONDS_MIN,
    SMTP_TEXT_MAX_LENGTH,
    is_valid_smtp_host,
)

# Notes on blocked numbers are short labels like "robocaller" or "wrong number".
BLOCKED_NOTE_MAX_LENGTH = 200
from app.utils.voices import DEFAULT_IVR_VOICE, ivr_voice_grouped_choices


class LoginForm(FlaskForm):
    username = StringField(
        "Username",
        validators=[DataRequired(), Length(max=64)],
    )
    password = PasswordField(
        "Password",
        validators=[DataRequired(), Length(max=128)],
    )
    submit = SubmitField("Sign in")


class SettingsForm(FlaskForm):
    greeting = TextAreaField(
        "Main menu greeting",
        validators=[DataRequired(), Length(max=IVR_TEXT_MAX_LENGTH)],
    )
    invalid_digit_message = TextAreaField(
        "Invalid input message",
        validators=[DataRequired(), Length(max=IVR_TEXT_MAX_LENGTH)],
    )
    voicemail_prompt = TextAreaField(
        "Voicemail prompt",
        validators=[DataRequired(), Length(max=IVR_TEXT_MAX_LENGTH)],
    )
    voicemail_thanks = TextAreaField(
        "Thank-you message",
        validators=[DataRequired(), Length(max=IVR_TEXT_MAX_LENGTH)],
    )
    ivr_voice = SelectField(
        "IVR voice",
        choices=ivr_voice_grouped_choices(),
        validators=[DataRequired()],
        default=DEFAULT_IVR_VOICE,
    )
    max_recording_seconds = IntegerField(
        "Max recording length (seconds)",
        validators=[
            DataRequired(),
            NumberRange(min=MAX_RECORDING_SECONDS_MIN, max=MAX_RECORDING_SECONDS_MAX),
        ],
    )
    transcription_enabled = BooleanField("Enable voicemail transcription")
    personalized_greeting_enabled = BooleanField("Enable personalized greetings")
    smtp_host = StringField(
        "SMTP host",
        validators=[Optional(), Length(max=SMTP_TEXT_MAX_LENGTH)],
    )
    smtp_port = SelectField(
        "SMTP security",
        choices=[("465", "SSL (port 465)"), ("587", "STARTTLS (port 587)")],
        default="465",
        validators=[Optional()],
    )
    smtp_user = StringField(
        "SMTP username",
        validators=[Optional(), Length(max=SMTP_TEXT_MAX_LENGTH)],
    )
    smtp_password = PasswordField(
        "SMTP password",
        validators=[Optional(), Length(max=255)],
    )
    smtp_from = StringField(
        "From address",
        validators=[Optional(), Length(max=SMTP_TEXT_MAX_LENGTH)],
    )
    block_action = SelectField(
        "Blocked caller handling",
        choices=[
            ("reject", "Reject the call (busy signal, no audio)"),
            ("message", "Play a message, then hang up"),
        ],
        validators=[DataRequired()],
        default="reject",
    )
    blocked_caller_message = TextAreaField(
        "Blocked caller message",
        validators=[Optional(), Length(max=IVR_TEXT_MAX_LENGTH)],
    )
    submit = SubmitField("Save settings")

    def validate_block_action(self, field):
        if field.data not in BLOCK_ACTIONS:
            raise ValidationError("Invalid blocked caller handling option.")

    def validate_smtp_host(self, field):
        if field.data and not is_valid_smtp_host(field.data):
            raise ValidationError(
                "Enter a valid mail server hostname, e.g. smtp.fastmail.com."
            )

    def validate_smtp_user(self, field):
        if field.data and not is_valid_email(field.data):
            raise ValidationError(
                "The SMTP username should be your full Fastmail email address."
            )

    def validate_smtp_from(self, field):
        if field.data and not is_valid_email(field.data):
            raise ValidationError("Enter a valid From email address.")


class BoxForm(FlaskForm):
    """Edit a single voicemail box (Family, Cody, Ryan, Cory)."""

    display_name = StringField(
        "Display name",
        validators=[DataRequired(), Length(max=CONTACT_NAME_MAX_LENGTH)],
    )
    extension_digit = SelectField(
        "Menu digit",
        choices=[(str(n), str(n)) for n in range(1, 10)],
        validators=[DataRequired()],
    )
    voicemail_prompt = TextAreaField(
        "Voicemail prompt",
        validators=[Optional(), Length(max=IVR_TEXT_MAX_LENGTH)],
    )
    voicemail_thanks = TextAreaField(
        "Thank-you message",
        validators=[Optional(), Length(max=IVR_TEXT_MAX_LENGTH)],
    )
    is_child = BooleanField("Child mailbox")
    enabled = BooleanField("Enabled")
    submit = SubmitField("Save box")


class DeleteMessageForm(FlaskForm):
    """CSRF-only form backing the delete button/confirm action."""

    submit = SubmitField("Delete")


class MarkAllReadForm(FlaskForm):
    """CSRF-only form for the 'mark all read' action."""

    submit = SubmitField("Mark all read")


class ContactForm(FlaskForm):
    """Add or edit a single contact (phone -> display name)."""

    phone = StringField(
        "Phone number",
        validators=[DataRequired(), Length(max=32)],
    )
    display_name = StringField(
        "Display name",
        validators=[DataRequired(), Length(max=CONTACT_NAME_MAX_LENGTH)],
    )
    is_vip = BooleanField("VIP contact (bypasses blocklist)")
    email = StringField(
        "Email address",
        validators=[Optional(), Length(max=EMAIL_MAX_LENGTH)],
    )
    is_admin = BooleanField("Receive Family mailbox notifications")
    is_parent = BooleanField("Parent account")
    # Choices are populated per-request in the route ("" = no linked box).
    box_id = SelectField(
        "Voicemail box",
        choices=[("", "— None —")],
        validators=[Optional()],
    )
    # Child mailboxes this parent is notified for; choices set per-request.
    child_box_ids = SelectMultipleField(
        "Child mailboxes",
        choices=[],
        validators=[Optional()],
    )
    submit = SubmitField("Save contact")

    def validate_phone(self, field):
        normalized = normalize_phone(field.data)
        if not normalized:
            raise ValidationError(
                "Enter a valid phone number, e.g. +15551234567 or 5551234567."
            )
        # Expose the normalized form so the handler can store it directly.
        field.data = normalized

    def validate_email(self, field):
        if field.data and not is_valid_email(field.data):
            raise ValidationError("Enter a valid email address, e.g. you@example.com.")

    def validate(self, extra_validators=None):
        if not super().validate(extra_validators):
            return False
        ok = True
        # A recipient needs somewhere to send: require an email whenever the
        # contact is an admin/parent or is linked to a voicemail box.
        if (
            self.is_admin.data or self.is_parent.data or self.box_id.data
        ) and not self.email.data:
            self.email.errors.append(
                "An email address is required for notification recipients."
            )
            ok = False
        # Child-mailbox assignments only make sense for a parent account.
        if self.child_box_ids.data and not self.is_parent.data:
            self.is_parent.errors.append(
                "Enable “Parent account” to assign child mailboxes."
            )
            ok = False
        return ok


class DeleteContactForm(FlaskForm):
    """CSRF-only form backing the contact delete action."""

    submit = SubmitField("Delete")


class ContactsImportForm(FlaskForm):
    """Upload a CSV address book (columns: phone, display_name)."""

    file = FileField(
        "CSV file",
        validators=[
            FileRequired(),
            FileAllowed(["csv"], "Upload a .csv file."),
        ],
    )
    submit = SubmitField("Import")


class BlockedNumberForm(FlaskForm):
    """Add or edit a single blocked number (phone -> optional note)."""

    phone = StringField(
        "Phone number",
        validators=[DataRequired(), Length(max=32)],
    )
    note = StringField(
        "Note",
        validators=[Optional(), Length(max=BLOCKED_NOTE_MAX_LENGTH)],
    )
    submit = SubmitField("Save")

    def validate_phone(self, field):
        normalized = normalize_phone(field.data)
        if not normalized:
            raise ValidationError(
                "Enter a valid phone number, e.g. +15551234567 or 5551234567."
            )
        # Expose the normalized form so the handler can store it directly.
        field.data = normalized


class BlockCallerForm(FlaskForm):
    """CSRF-only form for blocking a caller from a message.

    The phone number is taken from the recording server-side, never from the
    form, so it cannot be tampered with.
    """

    submit = SubmitField("Block this caller")


class DeleteBlockedForm(FlaskForm):
    """CSRF-only form backing the blocked-number delete action."""

    submit = SubmitField("Delete")


class ImportBlocklistForm(FlaskForm):
    """CSRF-only form for importing/removing the starter blocklist."""

    submit = SubmitField("Import starter blocklist")


class LogoutForm(FlaskForm):
    """CSRF-only form for the logout button."""

    submit = SubmitField("Log out")


class ConnectionTestForm(FlaskForm):
    """CSRF-only form for triggering connection diagnostics."""

    submit = SubmitField("Run tests")


class NotificationTestForm(FlaskForm):
    """CSRF-only form for sending a test email notification."""

    submit = SubmitField("Send test email")
