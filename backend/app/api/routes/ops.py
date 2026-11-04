import os
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Response, status
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.api.routes.research import get_session_factory
from app.auth.deps import get_current_owner
from app.core.config import get_settings
from app.db.session import get_db
from app.models import (
    AuditEvent, Device, DeviceTask, Owner, Project, ResearchTarget, StorageObject, UploadJob, VideoRender, YouTubeAccount,
)
from app.services import ops as ops_logic
from app.services.heartbeat import online_workers
from app.services.maintenance import run_backup
from app.services.storage import Storage, get_storage

router = APIRouter(prefix="/api", tags=["operations"])
QUEUES = ("default", "browser", "render")


def get_redis():
    import redis

    return redis.Redis.from_url(get_settings().redis_url, socket_connect_timeout=1, socket_timeout=1)


def _component(name, ok, detail=""):
    return {"name": name, "status": "ok" if ok else "down", "detail": detail}


@router.get("/system/health")
def system_health(owner: Owner = Depends(get_current_owner), db: Session = Depends(get_db),
                  storage: Storage = Depends(get_storage), redis_client=Depends(get_redis)):
    comps = []
    try:
        db.execute(text("SELECT 1"))
        comps.append(_component("database", True))
    except Exception as exc:
        comps.append(_component("database", False, type(exc).__name__))
    depths = {}
    try:
        redis_client.ping()
        comps.append(_component("redis", True))
        depths = {q: int(redis_client.llen(q)) for q in QUEUES}
    except Exception:
        comps.append(_component("redis", False, "not reachable (jobs run in-process if JOB_BACKEND=inprocess)"))
    try:
        key = f"{owner.id}/health/{uuid.uuid4()}.txt"
        storage.put(key, b"ok", "text/plain")
        storage.delete(key)
        comps.append(_component("storage", True, storage.backend))
    except Exception as exc:
        comps.append(_component("storage", False, f"{type(exc).__name__}: {exc}"[:120]))
    comps.append(_component("ffmpeg", bool(shutil.which("ffmpeg") and shutil.which("ffprobe")), "needed to render and validate audio"))
    browsers = Path(os.environ.get("PLAYWRIGHT_BROWSERS_PATH", Path.home() / ".cache" / "ms-playwright"))
    comps.append(_component("browser", browsers.exists() and any(browsers.glob("chromium*")), "Chromium for research and recording"))
    comps.append(_component("pg_dump", bool(shutil.which("pg_dump")), "needed for backups"))

    mine_proj = select(Project.id).where(Project.owner_id == owner.id)
    now = datetime.now(timezone.utc)
    stuck = {
        "renders": sum(1 for r in db.scalars(select(VideoRender).where(VideoRender.status == "rendering", VideoRender.project_id.in_(mine_proj))).all()
                       if ops_logic.is_stale(r.updated_at, "render_rendering", now)),
        "uploads": sum(1 for u in db.scalars(select(UploadJob).where(UploadJob.status == "uploading", UploadJob.project_id.in_(mine_proj))).all()
                       if ops_logic.is_stale(u.updated_at, "upload_uploading", now)),
        "device_tasks": sum(1 for t in db.scalars(select(DeviceTask).where(DeviceTask.status == "claimed", DeviceTask.project_id.in_(mine_proj))).all()
                            if ops_logic.is_stale(t.claimed_at or t.updated_at, "device_task_claimed", now)),
        "research": sum(1 for t in db.scalars(select(ResearchTarget).where(ResearchTarget.status == "running", ResearchTarget.project_id.in_(mine_proj))).all()
                        if ops_logic.is_stale(t.updated_at, "research_running", now)),
    }
    used = db.scalar(select(func.coalesce(func.sum(StorageObject.size_bytes), 0)).where(StorageObject.owner_id == owner.id)) or 0
    return {"components": comps, "workers_online": online_workers(), "queue_depth": depths, "stuck": stuck,
            "storage_bytes": used, "overall": "ok" if all(c["status"] == "ok" for c in comps if c["name"] in {"database", "storage"}) else "degraded"}


@router.post("/system/recover")
def recover(owner: Owner = Depends(get_current_owner), db: Session = Depends(get_db)):
    from app.services.maintenance import recover_stale

    return recover_stale(db)


@router.get("/security/checks")
def security_checks(owner: Owner = Depends(get_current_owner), db: Session = Depends(get_db)):
    s = get_settings()
    checks = ops_logic.security_checks({
        "app_env": s.app_env, "owner_email": s.owner_email, "token_encryption_key": s.token_encryption_key,
        "cors_origins": s.cors_origin_list, "frontend_url": s.frontend_base, "firebase_project_id": s.firebase_project_id,
        "firebase_credentials": s.firebase_credentials, "rate_limit_per_minute": s.rate_limit_per_minute,
        "job_backend": s.job_backend, "s3_bucket": s.s3_bucket, "database_url": s.database_url})
    needs = db.scalar(select(func.count()).select_from(YouTubeAccount).where(YouTubeAccount.owner_id == owner.id, YouTubeAccount.status == "reauthorize")) or 0
    if needs:
        checks.append({"name": "youtube_reconnect", "status": "warn", "detail": f"{needs} YouTube connection(s) need reconnecting"})
    old = [d for d in db.scalars(select(Device).where(Device.owner_id == owner.id, Device.revoked_at.is_(None))).all()
           if d.last_seen_at and (datetime.now(timezone.utc) - (d.last_seen_at if d.last_seen_at.tzinfo else d.last_seen_at.replace(tzinfo=timezone.utc))).days > 30]
    if old:
        checks.append({"name": "stale_devices", "status": "warn", "detail": f"{len(old)} paired computer(s) unused for 30+ days; revoke them if you no longer use them"})
    return checks


@router.get("/audit")
def audit_log(action: str | None = None, limit: int = 50, before: str | None = None,
              owner: Owner = Depends(get_current_owner), db: Session = Depends(get_db)):
    q = select(AuditEvent).where(AuditEvent.owner_id == owner.id)
    if action:
        q = q.where(AuditEvent.action.like(f"{action}%"))
    if before:
        try:
            q = q.where(AuditEvent.created_at < datetime.fromisoformat(before))
        except ValueError as exc:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "before must be an ISO timestamp") from exc
    rows = db.scalars(q.order_by(AuditEvent.created_at.desc()).limit(max(1, min(limit, 200)))).all()
    return [{"id": str(a.id), "action": a.action, "at": a.created_at.isoformat(), "ip": a.ip, "detail": a.detail} for a in rows]


# ---------- backups ----------
def _list_backups(db: Session, owner_id):
    return db.scalars(select(StorageObject).where(StorageObject.owner_id == owner_id, StorageObject.key.like("%/backups/%"))
                      .order_by(StorageObject.created_at.desc())).all()


@router.get("/backups")
def list_backups(owner: Owner = Depends(get_current_owner), db: Session = Depends(get_db)):
    return {"pg_dump_available": bool(shutil.which("pg_dump")), "database_is_postgres": get_settings().database_url.startswith("postgresql"),
            "items": [{"id": str(o.id), "size_bytes": o.size_bytes, "created_at": o.created_at.isoformat(), "sha256": o.sha256}
                      for o in _list_backups(db, owner.id)]}


def _backup_bg(session_factory, owner_id, storage):
    with session_factory() as db:
        try:
            run_backup(db, owner_id, storage, get_settings().database_url)
        except Exception:
            pass  # run_backup already recorded the failure as a notification and audit event


@router.post("/backups", status_code=status.HTTP_202_ACCEPTED)
def create_backup(tasks: BackgroundTasks, owner: Owner = Depends(get_current_owner), storage: Storage = Depends(get_storage),
                  session_factory=Depends(get_session_factory)):
    if not get_settings().database_url.startswith("postgresql"):
        raise HTTPException(status.HTTP_409_CONFLICT, "Backups need a PostgreSQL database")
    if not shutil.which("pg_dump"):
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "pg_dump is not installed in this environment")
    tasks.add_task(_backup_bg, session_factory, owner.id, storage)
    return {"status": "started"}


@router.get("/backups/{backup_id}/download")
def download_backup(backup_id: uuid.UUID, owner: Owner = Depends(get_current_owner), db: Session = Depends(get_db),
                    storage: Storage = Depends(get_storage)):
    o = db.scalar(select(StorageObject).where(StorageObject.id == backup_id, StorageObject.owner_id == owner.id,
                                              StorageObject.key.like("%/backups/%")))
    if o is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Backup not found")
    return Response(storage.get(o.key), media_type="application/octet-stream",
                    headers={"Content-Disposition": 'attachment; filename="hell-uploads.dump"', "X-Content-Type-Options": "nosniff"})
