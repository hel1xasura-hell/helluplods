import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException, Request, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.routes.research import _owned_target, get_session_factory
from app.auth.deps import audit, get_current_owner
from app.db.session import get_db
from app.models import Device, DeviceTask, Owner, Project, Recording, StorageObject
from app.services import devices as dev
from app.services.executor import NoLocalDevice, choose_executor
from app.services.recording import run_cloud_recording
from app.services.ssrf import UnsafeURL, validate_public_url
from app.services.storage import Storage, get_storage

router = APIRouter(prefix="/api", tags=["recordings"])


def get_recorder():
    return None  # real Playwright recorder; tests override


class RecordIn(BaseModel):
    duration_seconds: float = Field(default=10, ge=3, le=120)


def _local_device_online(db: Session, owner_id: uuid.UUID) -> bool:
    devices = db.scalars(select(Device).where(Device.owner_id == owner_id, Device.revoked_at.is_(None))).all()
    return any(dev.is_online(d.last_seen_at) for d in devices)


def _bg(session_factory, task_id, storage, recorder):
    with session_factory() as db:
        run_cloud_recording(db, task_id, storage, recorder)


@router.post("/targets/{target_id}/record", status_code=status.HTTP_202_ACCEPTED)
def start_recording(target_id: uuid.UUID, body: RecordIn, request: Request, tasks: BackgroundTasks,
                    owner: Owner = Depends(get_current_owner), db: Session = Depends(get_db),
                    storage: Storage = Depends(get_storage), recorder=Depends(get_recorder),
                    session_factory=Depends(get_session_factory)):
    target = _owned_target(target_id, owner, db)
    if target.kind not in {"website_url", "play_url"}:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Only URL targets can be recorded")
    try:
        validate_public_url(target.value)
    except UnsafeURL as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"URL rejected: {exc}") from exc
    active = db.scalar(select(DeviceTask).where(DeviceTask.target_id == target.id, DeviceTask.kind == "record",
                                                DeviceTask.status.in_(["queued", "claimed"])))
    if active is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "A recording is already queued or running for this target")
    project = db.get(Project, target.project_id)
    try:
        executor = choose_executor(project.execution_mode, "record", _local_device_online(db, owner.id))
    except NoLocalDevice as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    task = DeviceTask(project_id=project.id, target_id=target.id, kind="record", executor=executor,
                      payload={"url": target.value, "duration_seconds": body.duration_seconds})
    db.add(task)
    db.flush()
    audit(db, owner.id, "recording.requested", request, target_id=str(target.id), executor=executor)
    db.commit()
    if executor == "cloud":
        tasks.add_task(_bg, session_factory, task.id, storage, recorder)
    return {"task_id": str(task.id), "executor": executor, "status": "queued"}


@router.get("/recording-tasks")
def list_tasks(owner: Owner = Depends(get_current_owner), db: Session = Depends(get_db)):
    rows = db.scalars(select(DeviceTask).join(Project, Project.id == DeviceTask.project_id)
                      .where(Project.owner_id == owner.id).order_by(DeviceTask.created_at.desc()).limit(30)).all()
    return [{"id": str(t.id), "executor": t.executor, "status": t.status, "url": t.payload.get("url"),
             "error": t.error, "created_at": t.created_at.isoformat()} for t in rows]


@router.get("/recordings")
def list_recordings(owner: Owner = Depends(get_current_owner), db: Session = Depends(get_db)):
    rows = db.scalars(select(Recording).join(Project, Project.id == Recording.project_id)
                      .where(Project.owner_id == owner.id).order_by(Recording.created_at.desc()).limit(50)).all()
    return [{"id": str(r.id), "project_id": str(r.project_id), "source_url": r.source_url,
             "duration_seconds": r.duration_seconds, "executor": r.executor, "is_real_capture": r.is_real_capture,
             "width": r.width, "height": r.height, "created_at": r.created_at.isoformat()} for r in rows]


@router.get("/recordings/{recording_id}/file")
def recording_file(recording_id: uuid.UUID, range: str | None = Header(default=None),
                   owner: Owner = Depends(get_current_owner), db: Session = Depends(get_db),
                   storage: Storage = Depends(get_storage)):
    row = db.execute(select(Recording, StorageObject).join(Project, Project.id == Recording.project_id)
                     .join(StorageObject, StorageObject.id == Recording.storage_object_id)
                     .where(Recording.id == recording_id, Project.owner_id == owner.id)).first()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Recording not found")
    data = storage.get(row[1].key)
    total = len(data)
    headers = {"Accept-Ranges": "bytes", "X-Content-Type-Options": "nosniff"}
    if range and range.startswith("bytes="):
        try:
            start_s, _, end_s = range[6:].partition("-")
            start = int(start_s) if start_s else max(0, total - int(end_s))
            end = int(end_s) if end_s and start_s else total - 1
            end = min(end, total - 1)
            if start > end or start >= total:
                raise ValueError
        except ValueError:
            return Response(status_code=416, headers={"Content-Range": f"bytes */{total}"})
        headers["Content-Range"] = f"bytes {start}-{end}/{total}"
        return Response(data[start:end + 1], status_code=206, media_type="video/webm", headers=headers)
    return Response(data, media_type="video/webm", headers=headers)
