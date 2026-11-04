"""Create Recording rows from real captures (cloud recorder or uploaded by a paired device)."""
import asyncio
import tempfile
import uuid
from collections.abc import Awaitable, Callable
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy.orm import Session

from app.browser.recorder import RecordingRefused, RecordingResult, looks_like_video, record_tour
from app.models import DeviceTask, Notification, Project, Recording, StorageObject
from app.services.ssrf import UnsafeURL, validate_public_url
from app.services.storage import Storage

MAX_VIDEO_BYTES = 200 * 1024 * 1024
Recorder = Callable[..., Awaitable[RecordingResult]]


class InvalidVideo(ValueError):
    pass


def store_video(db: Session, project: Project, storage: Storage, data: bytes) -> StorageObject:
    if not data or len(data) > MAX_VIDEO_BYTES:
        raise InvalidVideo("Video is empty or too large")
    if not looks_like_video(data[:16]):
        raise InvalidVideo("File is not a WebM or MP4 video")
    key = f"{project.owner_id}/{project.id}/recordings/{uuid.uuid4()}.webm"
    meta = storage.put(key, data, "video/webm")
    obj = StorageObject(owner_id=project.owner_id, backend=storage.backend, key=key, content_type="video/webm",
                        size_bytes=meta["size_bytes"], sha256=meta["sha256"])
    db.add(obj)
    db.flush()
    return obj


def create_recording(db: Session, project: Project, obj: StorageObject, *, executor: str, source_url: str | None,
                     duration: float | None, width: int | None, height: int | None, actions: list) -> Recording:
    rec = Recording(project_id=project.id, storage_object_id=obj.id, duration_seconds=duration,
                    is_real_capture=True, executor=executor, source_url=source_url, width=width, height=height,
                    actions=actions[:500])
    db.add(rec)
    db.add(Notification(owner_id=project.owner_id, kind="recording", title="Recording ready",
                        body=(source_url or "")[:300]))
    db.flush()
    return rec


def run_cloud_recording(db: Session, task_id: uuid.UUID, storage: Storage, recorder: Recorder | None = None) -> None:
    task = db.get(DeviceTask, task_id)
    if task is None or task.executor != "cloud" or task.status != "queued":
        return
    project = db.get(Project, task.project_id)
    task.status, task.claimed_at = "claimed", datetime.now(timezone.utc)
    db.commit()
    recorder = recorder or record_tour
    try:
        with tempfile.TemporaryDirectory() as tmp:
            result = asyncio.run(recorder(task.payload["url"], Path(tmp), validate_public_url,
                                          duration_seconds=float(task.payload.get("duration_seconds", 10))))
            obj = store_video(db, project, storage, result.path.read_bytes())
        rec = create_recording(db, project, obj, executor="cloud", source_url=result.final_url,
                               duration=result.duration_seconds, width=result.width, height=result.height,
                               actions=result.actions)
        task.status, task.result = "done", {"recording_id": str(rec.id), "blocked": result.blocked_requests[:20]}
    except (UnsafeURL, RecordingRefused, InvalidVideo) as exc:
        task.status, task.error = "failed", str(exc)[:500]
    except Exception as exc:
        task.status, task.error = "failed", f"Recording failed: {type(exc).__name__}: {exc}"[:500]
    if task.status == "failed":
        db.add(Notification(owner_id=project.owner_id, kind="recording", title="Recording failed", body=task.error))
    db.commit()
