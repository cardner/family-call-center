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
    StringField,
    SubmitField,
    TextAreaField,
)
from wtforms.validators import DataRequired, Length, NumberRange, Optional, ValidationError

from app.utils.contacts import CONTACT_NAME_MAX_LENGTH
from app.utils.phone import normalize_phone
from app.utils.settings import (
    BLOCK_ACTIONS,
    IVR_TEXT_MAX_LENGTH,
    MAX_RECORDING_SECONDS_MAX,
    MAX_RECORDING_SECONDS_MIN,
    NOTIFY_PHONE_NUMBERS_MAX_LENGTH,
    is_valid_e164,
    parse_phone_numbers,
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
    notify_phone_numbers = TextAreaField(
        "SMS notification recipients",
        validators=[Optional(), Length(max=NOTIFY_PHONE_NUMBERS_MAX_LENGTH)],
    )
    transcription_enabled = BooleanField("Enable voicemail transcription")
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

    def validate_notify_phone_numbers(self, field):
        """Reject the whole field if any entry is not valid E.164."""
        invalid = [
            number
            for number in parse_phone_numbers(field.data)
            if not is_valid_e164(number)
        ]
        if invalid:
            raise ValidationError(
                "Invalid phone number(s): "
                + ", ".join(invalid)
                + ". Use E.164 format, e.g. +15551234567."
            )


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
    skip_ivr_menu = BooleanField("Skip the menu and go straight to voicemail")
    submit = SubmitField("Save contact")

    def validate_phone(self, field):
        normalized = normalize_phone(field.data)
        if not normalized:
            raise ValidationError(
                "Enter a valid phone number, e.g. +15551234567 or 5551234567."
            )
        # Expose the normalized form so the handler can store it directly.
        field.data = normalized


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
    """CSRF-only form for sending a test SMS notification."""

    submit = SubmitField("Send test SMS")
