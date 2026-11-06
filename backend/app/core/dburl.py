"""Normalise DATABASE_URL so the app, Alembic and workers always use the same PostgreSQL driver (psycopg 3).

Hosting providers (Railway, Heroku, Render) hand out plain 'postgresql://' or 'postgres://' URLs. SQLAlchemy reads a plain
'postgresql://' as 'use psycopg2', which this project does not install. We install psycopg 3 only, so rewrite to
'postgresql+psycopg://'. This module has no dependencies so it can be tested on its own, and it never includes the URL
(which contains the password) in an error message."""

PSYCOPG3 = "postgresql+psycopg://"
_REWRITE = ("postgres://", "postgresql://", "postgresql+psycopg2://", "postgresql+psycopg2cffi://", "postgresql+pg8000://")


def normalize_database_url(url: str) -> str:
    if not isinstance(url, str):
        raise ValueError("DATABASE_URL must be a text value")
    cleaned = url.strip().strip("'\"").strip()  # tolerate quotes/newlines pasted into a dashboard variable
    if not cleaned:
        raise ValueError("DATABASE_URL is empty")
    for prefix in _REWRITE:
        if cleaned.startswith(prefix):
            return PSYCOPG3 + cleaned[len(prefix):]
    return cleaned  # already postgresql+psycopg://, sqlite:// for tests, or something we deliberately leave alone
