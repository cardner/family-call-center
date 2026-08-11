"""Encryption for sensitive settings stored in the SQLite ``settings`` table.

Only a handful of settings hold secrets (the Fastmail SMTP credentials). Those
values are Fernet-encrypted before they touch the database and decrypted when
read by application code. The symmetric key lives in the environment
(``SETTINGS_ENCRYPTION_KEY``) and is never stored in the database, so a stolen
database file or backup does not expose the credentials.

Values carry a short prefix so an encrypted token is always distinguishable
from a legacy plaintext value written before encryption existed.
"""

import logging

from config import Config

logger = logging.getLogger(__name__)

# Marker prepended to every ciphertext so encrypted values can be detected
# without attempting decryption first.
_PREFIX = "enc::v1::"


class SettingsEncryptionError(RuntimeError):
    """Raised when a value must be encrypted but no key is configured."""


def _fernet():
    """Return a Fernet instance, or None when no key is configured."""
    key = Config.SETTINGS_ENCRYPTION_KEY
    if not key:
        return None
    from cryptography.fernet import Fernet

    if isinstance(key, str):
        key = key.encode()
    return Fernet(key)


def encryption_available():
    """Return True if a usable encryption key is configured."""
    try:
        return _fernet() is not None
    except Exception:  # noqa: BLE001 - a malformed key is treated as unavailable
        logger.warning("SETTINGS_ENCRYPTION_KEY is set but invalid", exc_info=True)
        return False


def is_encrypted_value(value):
    """Return True if ``value`` is one of our encrypted tokens."""
    return isinstance(value, str) and value.startswith(_PREFIX)


def encrypt_setting_value(plaintext):
    """Encrypt ``plaintext`` into a prefixed Fernet token.

    Raises ``SettingsEncryptionError`` when no key is configured.
    """
    fernet = _fernet()
    if fernet is None:
        raise SettingsEncryptionError(
            "SETTINGS_ENCRYPTION_KEY is not configured; cannot encrypt setting."
        )
    token = fernet.encrypt(str(plaintext).encode()).decode()
    return _PREFIX + token


def decrypt_setting_value(value):
    """Decrypt a prefixed token, or return None if it cannot be decrypted."""
    if not is_encrypted_value(value):
        return None
    fernet = _fernet()
    if fernet is None:
        return None
    try:
        return fernet.decrypt(value[len(_PREFIX):].encode()).decode()
    except Exception:  # noqa: BLE001 - wrong key or corrupt token
        logger.warning("Could not decrypt a stored setting value", exc_info=True)
        return None
