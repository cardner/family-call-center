"""WTForms for the admin UI.

Every mutating admin request goes through one of these forms, giving us CSRF
protection (via Flask-WTF) and server-side validation in one place. Handlers
must not read ``request.form`` directly.
"""

from flask_wtf import FlaskForm
from wtforms import (
    IntegerField,
    PasswordField,
    StringField,
    SubmitField,
    TextAreaField,
)
from wtforms.validators import DataRequired, Length, NumberRange

from app.utils.settings import (
    IVR_TEXT_MAX_LENGTH,
    MAX_RECORDING_SECONDS_MAX,
    MAX_RECORDING_SECONDS_MIN,
)


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
    max_recording_seconds = IntegerField(
        "Max recording length (seconds)",
        validators=[
            DataRequired(),
            NumberRange(min=MAX_RECORDING_SECONDS_MIN, max=MAX_RECORDING_SECONDS_MAX),
        ],
    )
    submit = SubmitField("Save settings")


class DeleteMessageForm(FlaskForm):
    """CSRF-only form backing the delete button/confirm action."""

    submit = SubmitField("Delete")


class LogoutForm(FlaskForm):
    """CSRF-only form for the logout button."""

    submit = SubmitField("Log out")


class ConnectionTestForm(FlaskForm):
    """CSRF-only form for triggering connection diagnostics."""

    submit = SubmitField("Run tests")
