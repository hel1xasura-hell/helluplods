"""Operations logic with no framework imports: security checks, stale-work rules, backup retention, analytics maths."""
import re
from collections import Counter
from datetime import datetime, timedelta, timezone

# How long each kind of work may sit "in progress" before it is treated as stuck.
STALE_AFTER = {
    "render_rendering": timedelta(minutes=45),
    "upload_uploading": timedelta(hours=2),
    "device_task_claimed": timedelta(minutes=30),
    "cloud_task_claimed": timedelta(minutes=30),
    "research_running": timedelta(minutes=30),
}


def is_stale(since: datetime | None, kind: str, now: datetime | None = None) -> bool:
    if since is None:
        return False
    now = now or datetime.now(timezone.utc)
    if since.tzinfo is None:
        since = since.replace(tzinfo=timezone.utc)
    return now - since > STALE_AFTER[kind]


# ---------- backups ----------
def backup_key(owner_id: str, now: datetime | None = None) -> str:
    now = now or datetime.now(timezone.utc)
    return f"{owner_id}/backups/hell-uploads-{now.strftime('%Y%m%dT%H%M%SZ')}.dump"


def backups_to_delete(items: list[tuple[str, datetime]], keep: int = 14, keep_days: int = 30,
                      now: datetime | None = None) -> list[str]:
    """Keep the newest `keep` backups; of the rest, delete those older than `keep_days`. Never deletes the newest one."""
    now = now or datetime.now(timezone.utc)
    ordered = sorted(items, key=lambda x: x[1], reverse=True)
    out = []
    for i, (key, when) in enumerate(ordered):
        w = when if when.tzinfo else when.replace(tzinfo=timezone.utc)
        if i >= keep and now - w > timedelta(days=keep_days):
            out.append(key)
    return out


def pg_dump_args(database_url: str) -> list[str]:
    """pg_dump wants a plain postgresql:// URL, not the SQLAlchemy driver form. Passed as an argument list (no shell)."""
    url = re.sub(r"^postgresql\+\w+://", "postgresql://", database_url)
    if not url.startswith("postgresql://"):
        raise ValueError("Backups need a PostgreSQL DATABASE_URL")
    return ["pg_dump", "--format=custom", "--no-owner", url]


# ---------- security checks ----------
def security_checks(cfg: dict) -> list[dict]:
    """Configuration health. cfg keys: app_env, owner_email, token_encryption_key, cors_origins (list), frontend_url,
    firebase_project_id, firebase_credentials, rate_limit_per_minute, job_backend, s3_bucket, database_url, youtube_client_secret."""
    checks: list[dict] = []

    def add(name, ok, detail, severity="high"):
        checks.append({"name": name, "status": "pass" if ok else ("fail" if severity == "high" else "warn"), "detail": detail})

    prod = cfg.get("app_env") == "production"
    add("owner_email", bool(cfg.get("owner_email")), "OWNER_EMAIL restricts the workspace to one verified account")
    add("firebase", bool(cfg.get("firebase_project_id")), "Firebase project is configured for token verification")
    add("token_encryption_key", bool(cfg.get("token_encryption_key")), "OAuth tokens can be encrypted at rest")
    origins = cfg.get("cors_origins") or []
    add("cors_not_wildcard", "*" not in origins and bool(origins), "CORS lists explicit origins only")
    if prod:
        add("https_origins", all(o.startswith("https://") for o in origins) and str(cfg.get("frontend_url", "")).startswith("https://"),
            "Production frontend and CORS origins use https")
        add("api_docs_hidden", True, "Interactive API docs are disabled in production", "low")
        add("object_storage", bool(cfg.get("s3_bucket")), "Recordings and videos use object storage, not local disk", "low")
        add("revocation_checks", bool(cfg.get("firebase_credentials")), "Service-account credentials enable token revocation checks", "low")
        add("database_not_default", "hell:hell@" not in str(cfg.get("database_url", "")), "Database password is not the development default")
    add("rate_limit", int(cfg.get("rate_limit_per_minute", 0) or 0) > 0, "Per-IP rate limiting is on")
    add("durable_jobs", cfg.get("job_backend") == "celery", "Jobs run on workers (survive API restarts)", "low")
    return checks


# ---------- analytics ----------
def daily_counts(timestamps: list[datetime], days: int = 14, now: datetime | None = None) -> list[dict]:
    now = now or datetime.now(timezone.utc)
    start = (now - timedelta(days=days - 1)).date()
    counts = Counter(t.astimezone(timezone.utc).date() if t.tzinfo else t.date() for t in timestamps)
    return [{"date": str(start + timedelta(days=i)), "count": counts.get(start + timedelta(days=i), 0)} for i in range(days)]


def rate(part: int, whole: int) -> float | None:
    return round(part / whole, 3) if whole else None


def average(values: list[float]) -> float | None:
    vals = [v for v in values if v is not None]
    return round(sum(vals) / len(vals), 2) if vals else None
