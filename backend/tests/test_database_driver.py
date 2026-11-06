"""One PostgreSQL driver (psycopg 3) everywhere: the app, Alembic and the workers."""
import pathlib
import re

import pytest

from app.core.dburl import normalize_database_url

ROOT = pathlib.Path(__file__).resolve().parents[2]


@pytest.mark.parametrize("raw,expected", [
    ("postgresql://u:p@host:5432/db", "postgresql+psycopg://u:p@host:5432/db"),                 # what Railway provides
    ("postgres://u:p@host/db", "postgresql+psycopg://u:p@host/db"),                              # Heroku-style
    ("postgresql+psycopg2://u:p@host/db", "postgresql+psycopg://u:p@host/db"),                   # never psycopg2
    ("postgresql+psycopg://u:p@host/db", "postgresql+psycopg://u:p@host/db"),                    # already correct
    ("  'postgresql://u:p@host/db'\n", "postgresql+psycopg://u:p@host/db"),                      # pasted with quotes/newline
    ("postgresql://u:p@host/db?sslmode=require", "postgresql+psycopg://u:p@host/db?sslmode=require"),
    ("sqlite://", "sqlite://"),                                                                  # tests keep working
])
def test_normalize_database_url(raw, expected):
    assert normalize_database_url(raw) == expected


def test_errors_never_leak_the_password():
    for bad in ("", "   ", "''"):
        try:
            normalize_database_url(bad)
            raise AssertionError(f"{bad!r} should be rejected")
        except ValueError as exc:
            assert "p@ss" not in str(exc) and "postgres" not in str(exc).lower().replace("database_url", "")
    with pytest.raises(ValueError):
        normalize_database_url(None)  # type: ignore[arg-type]


def test_settings_applies_the_normaliser_for_env_values(monkeypatch):
    from app.core.config import Settings

    assert Settings(database_url="postgresql://u:p@h:5432/d").database_url == "postgresql+psycopg://u:p@h:5432/d"
    monkeypatch.setenv("DATABASE_URL", "postgres://u:p@h/d")
    assert Settings().database_url == "postgresql+psycopg://u:p@h/d"


def test_alembic_and_runtime_read_the_normalised_url():
    env = (ROOT / "backend/alembic/env.py").read_text()
    session = (ROOT / "backend/app/db/session.py").read_text()
    assert env.count("get_settings().database_url") == 2 and "os.environ" not in env  # not reading the raw env var
    assert "get_settings().database_url" in session


def test_only_psycopg3_is_a_dependency_anywhere():
    reqs = (ROOT / "backend/requirements.txt").read_text()
    assert re.search(r"^psycopg\[binary\]==3\.", reqs, re.M), "psycopg 3 with bundled libpq must be a production dependency"
    for path in ROOT.rglob("*"):
        if path.is_file() and path.suffix in {".txt", ".toml", ".cfg"} or path.name.startswith("Dockerfile"):
            if any(part in {"node_modules", ".git", "__pycache__"} for part in path.parts):
                continue
            assert "psycopg2" not in path.read_text(errors="ignore"), f"psycopg2 referenced in {path}"


def test_every_image_installs_the_same_requirements_file():
    for name in ("backend/Dockerfile", "workers/Dockerfile.default", "workers/Dockerfile.browser", "workers/Dockerfile.render"):
        text = (ROOT / name).read_text()
        assert "pip install --no-cache-dir -r requirements.txt" in text, name
        assert "requirements.txt" in text and "requirements-dev" not in text, name  # production images use production deps only
