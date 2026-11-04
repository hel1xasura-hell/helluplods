"""Scheduled maintenance: recover stuck work, take database backups, apply retention."""
import subprocess
import uuid
from collections.abc import Callable
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    AgentRun, AuditEvent, DeviceTask, Notification, Owner, ResearchTarget, StorageObject, UploadJob, VideoRender,
)
from app.services import ops
from app.services.storage import Storage


def recover_stale(db: Session, now: datetime | None = None) -> dict[str, int]:
    """Mark work that has been 'in progress' too long as failed, so nothing hangs forever and the owner can retry.
    Uploads keep their saved session, so a retry resumes instead of restarting."""
    now = now or datetime.now(timezone.utc)
    counts = {"renders": 0, "uploads": 0, "device_tasks": 0, "cloud_tasks": 0, "research": 0}

    for r in db.scalars(select(VideoRender).where(VideoRender.status == "rendering")).all():
        if ops.is_stale(r.updated_at, "render_rendering", now):
            r.status, r.error = "failed", "The render stopped responding and was marked failed. Render again."
            counts["renders"] += 1
    for j in db.scalars(select(UploadJob).where(UploadJob.status == "uploading")).all():
        if ops.is_stale(j.updated_at, "upload_uploading", now):
            j.status, j.error = "failed", "The upload stalled. Retry to resume where it stopped."
            counts["uploads"] += 1
    for t in db.scalars(select(DeviceTask).where(DeviceTask.status == "claimed")).all():
        kind = "device_task_claimed" if t.executor == "local" else "cloud_task_claimed"
        if ops.is_stale(t.claimed_at or t.updated_at, kind, now):
            t.status, t.error = "failed", "The task was claimed but never finished."
            counts["device_tasks" if t.executor == "local" else "cloud_tasks"] += 1
    for t in db.scalars(select(ResearchTarget).where(ResearchTarget.status == "running")).all():
        if ops.is_stale(t.updated_at, "research_running", now):
            t.status, t.error = "failed", "Research stopped responding. Run it again."
            counts["research"] += 1
    for run in db.scalars(select(AgentRun).where(AgentRun.status.in_(["running", "paused"]))).all():
        if ops.is_stale(run.updated_at, "research_running", now) and run.status == "running":
            run.status, run.error = "failed", run.error or "Marked failed after stalling."
    total = sum(counts.values())
    if total:
        owner = db.scalar(select(Owner))
        if owner:
            db.add(Notification(owner_id=owner.id, kind="system", title="Recovered stuck work",
                                body=", ".join(f"{v} {k.replace('_', ' ')}" for k, v in counts.items() if v)))
    db.commit()
    return counts


Runner = Callable[[list[str]], bytes]


def _pg_dump(args: list[str]) -> bytes:
    proc = subprocess.run(args, capture_output=True, timeout=1800)
    if proc.returncode != 0:
        raise RuntimeError(f"pg_dump failed: {proc.stderr.decode(errors='replace')[-300:]}")
    return proc.stdout


def run_backup(db: Session, owner_id: uuid.UUID, storage: Storage, database_url: str, runner: Runner | None = None,
               keep: int = 14, keep_days: int = 30, now: datetime | None = None) -> StorageObject:
    """Dump the database, verify it looks like a pg_dump archive, store it, apply retention."""
    now = now or datetime.now(timezone.utc)
    args = ops.pg_dump_args(database_url)
    try:
        data = (runner or _pg_dump)(args)
        if not data.startswith(b"PGDMP"):
            raise RuntimeError("The dump is not a valid PostgreSQL archive")
        key = ops.backup_key(str(owner_id), now)
        meta = storage.put(key, data, "application/octet-stream")
    except Exception as exc:
        db.add(Notification(owner_id=owner_id, kind="system", title="Backup failed", body=str(exc)[:300]))
        db.add(AuditEvent(owner_id=owner_id, action="backup.failed", detail={"error": str(exc)[:300]}))
        db.commit()
        raise
    obj = StorageObject(owner_id=owner_id, backend=storage.backend, key=key, content_type="application/octet-stream",
                        size_bytes=meta["size_bytes"], sha256=meta["sha256"])
    db.add(obj)
    db.add(AuditEvent(owner_id=owner_id, action="backup.created", detail={"bytes": meta["size_bytes"]}))
    db.flush()
    existing = db.scalars(select(StorageObject).where(StorageObject.owner_id == owner_id,
                                                      StorageObject.key.like("%/backups/%"))).all()
    doomed = set(ops.backups_to_delete([(o.key, o.created_at) for o in existing], keep, keep_days, now))
    for o in existing:
        if o.key in doomed:
            storage.delete(o.key)
            db.delete(o)
    db.commit()
    return obj
