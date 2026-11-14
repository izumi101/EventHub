"""Encryption at rest for TOTP secrets.

Fernet (AES-128-CBC + HMAC-SHA256) under keys derived with HKDF-SHA256 from
settings.MFA_ENCRYPTION_KEYS. The first key encrypts; every key decrypts, so
a key is rotated by putting the new one first (`MFA_ENCRYPTION_KEY=new,old`).
A secret still encrypted with an old key is re-encrypted with the current one
the next time it is verified (mfa/totp.py); drop the old key after that.
"""

import base64
from functools import lru_cache

from cryptography.fernet import Fernet, InvalidToken, MultiFernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from django.conf import settings

_HKDF_INFO = b'eventhub-mfa-totp-secret-v1'


class SecretDecryptionError(Exception):
    """The stored secret can't be decrypted with any configured key."""


def _derive(key: str) -> bytes:
    raw = HKDF(algorithm=hashes.SHA256(), length=32, salt=None, info=_HKDF_INFO).derive(key.encode())
    return base64.urlsafe_b64encode(raw)


@lru_cache(maxsize=4)
def _fernet(keys: tuple[str, ...]) -> MultiFernet:
    return MultiFernet([Fernet(_derive(k)) for k in keys])


def _current() -> MultiFernet:
    return _fernet(tuple(settings.MFA_ENCRYPTION_KEYS))


def encrypt_secret(secret: str) -> str:
    return _current().encrypt(secret.encode()).decode()


def decrypt_secret(token: str) -> str:
    try:
        return _current().decrypt(token.encode()).decode()
    except InvalidToken as exc:
        raise SecretDecryptionError('TOTP secret cannot be decrypted with MFA_ENCRYPTION_KEY') from exc


def needs_rotation(token: str) -> bool:
    """True when the secret was encrypted with an older key."""
    keys = settings.MFA_ENCRYPTION_KEYS
    if len(keys) < 2:
        return False
    try:
        Fernet(_derive(keys[0])).decrypt(token.encode())
    except InvalidToken:
        return True
    return False
