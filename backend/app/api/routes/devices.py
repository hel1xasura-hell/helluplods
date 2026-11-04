import time
import uuid
from collections import defaultdict, deque
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.auth.deps import audit, get_current_owner
from app.db.session import get_db
from app.models import Device, DevicePairingCode, DeviceTask, Owner, Project
from app.services import devices as dev
from app.services.recording import InvalidVideo, create_recording, store_video
from app.services.storage import Storage, get_storage

router = APIRouter(tags=["devices"])

_attempts: dict[str, deque[float]] = defaultdict(deque)
MAX_PAIR_ATTEMPTS, PAIR_WINDOW = 8, 600


def _throttle_pairing(ip: str) -> None:
    now, q = time.monotonic(), _attempts[ip]
    while q and now - q[0] > PAIR_WINDOW:
        q.popleft()
    if len(q) >= MAX_PAIR_ATTEMPTS:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Too many pairing attempts. Try again later.")
    q.append(now)


# ---------- owner side ----------
@router.post("/api/devices/pairing-codes", status_code=status.HTTP_201_CREATED)
def create_pairing_code(request: Request, owner: Owner = Depends(get_current_owner), db: Session = Depends(get_db)):
    code = dev.new_pairing_code()
    row = DevicePairingCode(owner_id=owner.id, code_hash=dev.hash_secret(code),
                            expires_at=datetime.now(timezone.utc) + dev.PAIRING_TTL)
    db.add(row)
    audit(db, owner.id, "device.pairing_code_created", request)
    db.commit()
    return {"code": code, "expires_at": row.expires_at.isoformat()}  # shown once, never stored in clear


@router.get("/api/devices")
def list_devices(owner: Owner = Depends(get_current_owner), db: Session = Depends(get_db)):
    rows = db.scalars(select(Device).where(Device.owner_id == owner.id).order_by(Device.created_at.desc())).all()
    return [{"id": str(d.id), "name": d.name, "platform": d.platform, "revoked": d.revoked_at is not None,
             "online": d.revoked_at is None and dev.is_online(d.last_seen_at),
             "last_seen_at": d.last_seen_at.isoformat() if d.last_seen_at else None} for d in rows]


@router.delete("/api/devices/{device_id}", status_code=status.HTTP_204_NO_CONTENT)
def revoke_device(device_id: uuid.UUID, request: Request, owner: Owner = Depends(get_current_owner),
                  db: Session = Depends(get_db)):
    d = db.scalar(select(Device).where(Device.id == device_id, Device.owner_id == owner.id))
    if d is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Device not found")
    d.revoked_at, d.credential_hash = datetime.now(timezone.utc), None
    # queued/claimed work for this device goes back to failed so nothing is silently lost
    db.execute(update(DeviceTask).where(DeviceTask.device_id == d.id, DeviceTask.status == "claimed")
               .values(status="failed", error="Device was revoked"))
    audit(db, owner.id, "device.revoked", request, device_id=str(d.id))
    db.commit()


# ---------- pairing (device has no credential yet; the one-time code is the proof) ----------
class PairIn(BaseModel):
    code: str = Field(min_length=6, max_length=20)
    name: str = Field(min_length=1, max_length=120)
    platform: str = Field(pattern="^(windows|macos|linux)$")


@router.post("/api/devices/pair", status_code=status.HTTP_201_CREATED)
def pair_device(body: PairIn, request: Request, db: Session = Depends(get_db)):
    _throttle_pairing(request.client.host if request.client else "unknown")
    now = datetime.now(timezone.utc)
    row = db.scalar(select(DevicePairingCode).where(
        DevicePairingCode.code_hash == dev.hash_secret(dev.normalise_code(body.code)),
        DevicePairingCode.used_at.is_(None)))
    expires = row.expires_at.replace(tzinfo=timezone.utc) if row and row.expires_at.tzinfo is None else (row.expires_at if row else None)
    if row is None or expires < now:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid or expired pairing code")
    claimed = db.execute(update(DevicePairingCode).where(DevicePairingCode.id == row.id,
                                                         DevicePairingCode.used_at.is_(None)).values(used_at=now))
    if claimed.rowcount != 1:  # someone else used it in the meantime
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid or expired pairing code")
    credential = dev.new_device_credential()
    device = Device(owner_id=row.owner_id, name=body.name, platform=body.platform,
                    credential_hash=dev.hash_secret(credential), last_seen_at=now)
    db.add(device)
    db.flush()
    audit(db, row.owner_id, "device.paired", request, device_id=str(device.id), platform=body.platform)
    db.commit()
    return {"device_id": str(device.id), "credential": credential}  # the only time the credential is shown


# ---------- device side ----------
def get_device(request: Request, authorization: str | None = Header(default=None), db: Session = Depends(get_db)) -> Device:
    scheme, _, token = (authorization or "").partition(" ")
    if scheme != "Device" or not token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing device credential")
    d = db.scalar(select(Device).where(Device.credential_hash == dev.hash_secret(token), Device.revoked_at.is_(None)))
    if d is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or revoked device credential")
    d.last_seen_at = datetime.now(timezone.utc)
    db.commit()
    return d


@router.post("/api/device/heartbeat", status_code=status.HTTP_204_NO_CONTENT)
def heartbeat(_: Device = Depends(get_device)):
    return None


@router.post("/api/device/tasks/claim")
def claim_task(device: Device = Depends(get_device), db: Session = Depends(get_db)):
    """Atomically claim the oldest queued local task belonging to this device's owner."""
    for _ in range(3):
        task = db.scalar(
            select(DeviceTask).join(Project, Project.id == DeviceTask.project_id)
            .where(Project.owner_id == device.owner_id, DeviceTask.executor == "local", DeviceTask.status == "queued")
            .order_by(DeviceTask.created_at).limit(1))
        if task is None:
            return {"task": None}
        won = db.execute(update(DeviceTask).where(DeviceTask.id == task.id, DeviceTask.status == "queued")
                         .values(status="claimed", device_id=device.id, claimed_at=datetime.now(timezone.utc)))
        db.commit()
        if won.rowcount == 1:
            return {"task": {"id": str(task.id), "kind": task.kind, **task.payload}}
    return {"task": None}


def _my_task(task_id: uuid.UUID, device: Device, db: Session) -> DeviceTask:
    t = db.scalar(select(DeviceTask).where(DeviceTask.id == task_id, DeviceTask.device_id == device.id,
                                           DeviceTask.status == "claimed"))
    if t is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Task not found")
    return t


@router.put("/api/device/tasks/{task_id}/file")
async def upload_file(task_id: uuid.UUID, request: Request, device: Device = Depends(get_device),
                      db: Session = Depends(get_db), storage: Storage = Depends(get_storage)):
    task = _my_task(task_id, device, db)
    data = await request.body()
    project = db.get(Project, task.project_id)
    try:
        obj = store_video(db, project, storage, data)
    except InvalidVideo as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
    task.result = {**(task.result or {}), "storage_object_id": str(obj.id)}
    db.commit()
    return {"stored": True, "size_bytes": obj.size_bytes}


class CompleteIn(BaseModel):
    duration_seconds: float | None = Field(default=None, ge=0, le=7200)
    width: int | None = Field(default=None, ge=1, le=8192)
    height: int | None = Field(default=None, ge=1, le=8192)
    final_url: str | None = Field(default=None, max_length=2048)
    actions: list[dict] = Field(default_factory=list, max_length=500)


@router.post("/api/device/tasks/{task_id}/complete")
def complete_task(task_id: uuid.UUID, body: CompleteIn, device: Device = Depends(get_device),
                  db: Session = Depends(get_db)):
    from app.models import StorageObject

    task = _my_task(task_id, device, db)
    obj_id = (task.result or {}).get("storage_object_id")
    if not obj_id:
        raise HTTPException(status.HTTP_409_CONFLICT, "Upload the recording file first")
    project = db.get(Project, task.project_id)
    obj = db.get(StorageObject, uuid.UUID(obj_id))
    rec = create_recording(db, project, obj, executor="local", source_url=body.final_url or task.payload.get("url"),
                           duration=body.duration_seconds, width=body.width, height=body.height, actions=body.actions)
    task.status, task.result = "done", {**task.result, "recording_id": str(rec.id)}
    db.commit()
    return {"recording_id": str(rec.id)}


class FailIn(BaseModel):
    error: str = Field(max_length=500)


@router.post("/api/device/tasks/{task_id}/fail", status_code=status.HTTP_204_NO_CONTENT)
def fail_task(task_id: uuid.UUID, body: FailIn, device: Device = Depends(get_device), db: Session = Depends(get_db)):
    task = _my_task(task_id, device, db)
    task.status, task.error = "failed", body.error
    db.commit()
