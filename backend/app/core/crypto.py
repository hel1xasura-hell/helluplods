"""Encryption for secrets stored in the database (OAuth tokens)."""
from cryptography.fernet import Fernet, InvalidToken

from app.core.config import get_settings


class CryptoNotConfigured(RuntimeError):
    pass


def _fernet() -> Fernet:
    key = get_settings().token_encryption_key
    if not key:
        raise CryptoNotConfigured("TOKEN_ENCRYPTION_KEY is not set; cannot store OAuth tokens.")
    return Fernet(key.encode())


def encrypt(value: str) -> str:
    return _fernet().encrypt(value.encode()).decode()


def decrypt(value: str) -> str:
    try:
        return _fernet().decrypt(value.encode()).decode()
    except InvalidToken as exc:
        raise ValueError("Stored secret could not be decrypted with the current key.") from exc
