"""Device pairing and credentials. Secrets are random, shown once, stored only as SHA-256 hashes."""
import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone

PAIRING_TTL = timedelta(minutes=10)
ONLINE_WINDOW = timedelta(seconds=90)
ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"  # no look-alike characters


def hash_secret(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def new_pairing_code() -> str:
    raw = "".join(secrets.choice(ALPHABET) for _ in range(10))
    return f"{raw[:5]}-{raw[5:]}"


def normalise_code(code: str) -> str:
    return code.strip().upper().replace(" ", "")


def new_device_credential() -> str:
    return "hud_" + secrets.token_urlsafe(32)


def secrets_equal(a: str, b: str) -> bool:
    return hmac.compare_digest(a.encode(), b.encode())


def is_online(last_seen: datetime | None, now: datetime | None = None) -> bool:
    if last_seen is None:
        return False
    now = now or datetime.now(timezone.utc)
    if last_seen.tzinfo is None:
        last_seen = last_seen.replace(tzinfo=timezone.utc)
    return now - last_seen <= ONLINE_WINDOW
