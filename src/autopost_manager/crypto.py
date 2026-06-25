from __future__ import annotations

import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken

from autopost_manager.config import get_settings

ENCRYPTED_PREFIX = "enc:v1:"


def _derived_local_key(secret: str) -> bytes:
    digest = hashlib.sha256(secret.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest)


def _fernet() -> Fernet:
    settings = get_settings()
    key = settings.app_encryption_key
    if not key and settings.app_env == "local":
        key = _derived_local_key(settings.app_secret).decode("ascii")
    if not key:
        raise RuntimeError("APP_ENCRYPTION_KEY is required for encrypted Telegram sessions")
    return Fernet(key.encode("ascii"))


def encrypt_session_string(session_string: str | None) -> str | None:
    if not session_string:
        return None
    if session_string.startswith(ENCRYPTED_PREFIX):
        return session_string
    token = _fernet().encrypt(session_string.encode("utf-8")).decode("ascii")
    return f"{ENCRYPTED_PREFIX}{token}"


def decrypt_session_string(value: str | None) -> str:
    if not value:
        return ""
    if not value.startswith(ENCRYPTED_PREFIX):
        return value
    token = value[len(ENCRYPTED_PREFIX) :].encode("ascii")
    try:
        return _fernet().decrypt(token).decode("utf-8")
    except InvalidToken as exc:
        raise RuntimeError("Encrypted Telegram session cannot be decrypted") from exc
