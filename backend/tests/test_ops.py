import importlib.util
import pathlib
from datetime import datetime, timedelta, timezone

import pytest

from app.services import ops

NOW = datetime(2026, 11, 3, 12, 0, tzinfo=timezone.utc)
_spec = importlib.util.spec_from_file_location("preflight", pathlib.Path(__file__).resolve().parents[2] / "scripts" / "preflight.py")
preflight = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(preflight)

GOOD_ENV = {
    "APP_ENV": "production", "DATABASE_URL": "postgresql+psycopg://u:strongpw@db/app", "REDIS_URL": "redis://r", "OWNER_EMAIL": "me@x.com",
    "FIREBASE_PROJECT_ID": "p", "FIREBASE_CREDENTIALS": "/c.json", "TOKEN_ENCRYPTION_KEY": "x" * 43 + "=", "CORS_ORIGINS": "https://app.example.com",
    "FRONTEND_URL": "https://app.example.com", "JOB_BACKEND": "celery", "S3_BUCKET": "b",
}


def test_staleness_thresholds():
    assert ops.is_stale(NOW - timedelta(hours=1), "render_rendering", NOW)
    assert not ops.is_stale(NOW - timedelta(minutes=10), "render_rendering", NOW)
    assert not ops.is_stale(None, "upload_uploading", NOW)
    assert ops.is_stale(datetime(2026, 11, 3, 8, 0), "device_task_claimed", NOW)  # naive timestamps are treated as UTC


def test_backup_retention_keeps_recent_and_newest():
    items = [(f"k{i}", NOW - timedelta(days=i)) for i in range(0, 60, 2)]
    gone = ops.backups_to_delete(items, keep=5, keep_days=30, now=NOW)
    assert "k0" not in gone and "k2" not in gone and "k8" not in gone      # newest five survive
    assert "k10" not in gone and "k58" in gone and "k40" in gone           # within 30 days kept, older removed
    assert ops.backups_to_delete([("only", NOW - timedelta(days=400))], keep=1, now=NOW) == []   # never delete the newest


def test_backup_key_and_dump_args_are_safe():
    assert ops.backup_key("o1", NOW) == "o1/backups/hell-uploads-20261103T120000Z.dump"
    assert ops.pg_dump_args("postgresql+psycopg://u:p@h/db")[-1] == "postgresql://u:p@h/db"
    assert ops.pg_dump_args("postgresql://u:p@h/db")[:2] == ["pg_dump", "--format=custom"]
    with pytest.raises(ValueError):
        ops.pg_dump_args("sqlite:///x.db")
    with pytest.raises(ValueError):
        ops.pg_dump_args("mysql://h/db")


def _cfg(**kw):
    base = dict(app_env="production", owner_email="me@x.com", token_encryption_key="k", cors_origins=["https://a.example"],
                frontend_url="https://a.example", firebase_project_id="p", firebase_credentials="/c", rate_limit_per_minute=100,
                job_backend="celery", s3_bucket="b", database_url="postgresql://u:strong@h/d")
    base.update(kw)
    return {c["name"]: c["status"] for c in ops.security_checks(base)}


def test_security_checks_pass_and_fail_correctly():
    assert set(_cfg().values()) == {"pass"}
    assert _cfg(cors_origins=["*"])["cors_not_wildcard"] == "fail"
    assert _cfg(cors_origins=["http://a.example"])["https_origins"] == "fail"
    assert _cfg(owner_email="")["owner_email"] == "fail"
    assert _cfg(database_url="postgresql://hell:hell@h/d")["database_not_default"] == "fail"
    assert _cfg(job_backend="inprocess")["durable_jobs"] == "warn"
    assert _cfg(s3_bucket="")["object_storage"] == "warn"
    assert "https_origins" not in _cfg(app_env="development")


def test_daily_counts_fill_gaps_and_order():
    ts = [NOW, NOW - timedelta(hours=2), NOW - timedelta(days=2)]
    series = ops.daily_counts(ts, days=4, now=NOW)
    assert [s["count"] for s in series] == [0, 1, 0, 2] and series[-1]["date"] == "2026-11-03"
    assert ops.rate(1, 4) == 0.25 and ops.rate(1, 0) is None
    assert ops.average([2, 4, None]) == 3 and ops.average([]) is None


def test_preflight_accepts_good_env_and_rejects_bad_ones():
    assert not [r for r in preflight.run(GOOD_ENV) if r[0] == "FAIL"]
    bad = {**GOOD_ENV, "APP_ENV": "development", "CORS_ORIGINS": "*", "DATABASE_URL": "postgresql://hell:hell@h/d", "TOKEN_ENCRYPTION_KEY": "short"}
    fails = {r[1] for r in preflight.run(bad) if r[0] == "FAIL"}
    assert {"APP_ENV", "CORS_ORIGINS", "DATABASE_URL", "TOKEN_ENCRYPTION_KEY"} <= fails
    assert any(r[1] == "FRONTEND_URL" for r in preflight.run({k: v for k, v in GOOD_ENV.items() if k != "FRONTEND_URL"}))
    warns = {r[1] for r in preflight.run({**GOOD_ENV, "JOB_BACKEND": "inprocess", "S3_BUCKET": ""}) if r[0] == "WARN"}
    assert {"JOB_BACKEND", "S3_BUCKET"} <= warns
    assert any(r[1] == "ANTHROPIC_API_KEY" for r in preflight.run({**GOOD_ENV, "ANTHROPIC_API_KEY": "changeme"}))
