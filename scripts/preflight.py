#!/usr/bin/env python3
"""Production preflight. Reads the environment and refuses to bless an unsafe configuration.
Usage:  APP_ENV=production python scripts/preflight.py        (exit code 1 on any failure)"""
import os
import sys
from urllib.parse import urlsplit

REQUIRED = ["DATABASE_URL", "REDIS_URL", "OWNER_EMAIL", "FIREBASE_PROJECT_ID", "TOKEN_ENCRYPTION_KEY", "CORS_ORIGINS", "FRONTEND_URL"]


def run(env: dict[str, str]) -> list[tuple[str, str, str]]:
    out: list[tuple[str, str, str]] = []

    def add(level, name, detail):
        out.append((level, name, detail))

    for k in REQUIRED:
        if not env.get(k):
            add("FAIL", k, "is not set")
    if env.get("APP_ENV") != "production":
        add("FAIL", "APP_ENV", "must be 'production' (docs endpoints and defaults differ otherwise)")
    origins = [o.strip() for o in env.get("CORS_ORIGINS", "").split(",") if o.strip()]
    if "*" in origins:
        add("FAIL", "CORS_ORIGINS", "must not contain *")
    for o in origins + ([env["FRONTEND_URL"]] if env.get("FRONTEND_URL") else []):
        p = urlsplit(o)
        if p.scheme != "https":
            add("FAIL", "https", f"{o} is not https")
    if "hell:hell@" in env.get("DATABASE_URL", ""):
        add("FAIL", "DATABASE_URL", "still uses the development password")
    key = env.get("TOKEN_ENCRYPTION_KEY", "")
    if key:
        try:
            import base64
            if len(base64.urlsafe_b64decode(key + "=" * (-len(key) % 4))) != 32:
                raise ValueError
        except Exception:
            add("FAIL", "TOKEN_ENCRYPTION_KEY", "is not a valid Fernet key (32 url-safe base64 bytes)")
    if env.get("JOB_BACKEND") != "celery":
        add("WARN", "JOB_BACKEND", "inprocess runs jobs inside the API; use celery in production")
    if not env.get("S3_BUCKET"):
        add("WARN", "S3_BUCKET", "not set: recordings and videos would fill local disk")
    if not env.get("FIREBASE_CREDENTIALS"):
        add("WARN", "FIREBASE_CREDENTIALS", "not set: revoked Firebase sessions are not detected")
    if env.get("YOUTUBE_CLIENT_ID") and not env.get("YOUTUBE_REDIRECT_URI", "").startswith("https://"):
        add("FAIL", "YOUTUBE_REDIRECT_URI", "must be an https URL registered in Google Cloud")
    for k in ("ANTHROPIC_API_KEY", "YOUTUBE_CLIENT_SECRET", "ELEVENLABS_API_KEY", "S3_SECRET_ACCESS_KEY"):
        v = env.get(k, "")
        if v and v.lower() in {"changeme", "secret", "test", "xxx", "your-key-here"}:
            add("FAIL", k, "looks like a placeholder")
    return out


def main() -> int:
    results = run(dict(os.environ))
    for level, name, detail in results:
        print(f"{level:4} {name}: {detail}")
    failed = any(level == "FAIL" for level, _, _ in results)
    print("\nPreflight FAILED" if failed else "\nPreflight passed" + (" with warnings" if results else ""))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
