import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.routes.research import get_session_factory
from app.api.routes.youtube import get_youtube_client
from app.auth.deps import audit, get_current_owner
from app.core.config import get_settings
from app.db.session import get_db
from app.integrations.youtube_client import YouTubeClient
from app.models import Approval, Owner, Project, Script, UploadJob, VideoRender, YouTubeAccount
from app.services import publishing as pub
from app.services.script_meta import script_context
from app.services.storage import Storage, get_storage

router = APIRouter(prefix="/api", tags=["publishing"])


def _http(exc: pub.PublishError) -> HTTPException:
    return HTTPException(exc.status, exc.args[0])


class DefaultsIn(BaseModel):
    visibility: str = Field(default="private", pattern="^(private|unlisted|public)$")
    made_for_kids: bool
    contains_synthetic_media: bool
    daily_limit: int = Field(default=3, ge=1, le=50)
    publish_hours_utc: list[int] = Field(default_factory=list, max_length=12)


@router.get("/publishing/defaults")
def get_defaults(owner: Owner = Depends(get_current_owner)):
    return pub.owner_defaults(owner)


@router.put("/publishing/defaults")
def put_defaults(body: DefaultsIn, request: Request, owner: Owner = Depends(get_current_owner), db: Session = Depends(get_db)):
    if any(not 0 <= h <= 23 for h in body.publish_hours_utc):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Hours must be between 0 and 23 (UTC)")
    owner.settings = {**(owner.settings or {}), "publish_defaults": body.model_dump()}
    audit(db, owner.id, "publishing.defaults_changed", request)
    db.commit()
    return owner.settings["publish_defaults"]


def serialize_approval(db: Session, ap: Approval) -> dict:
    r = db.get(VideoRender, ap.render_id) if ap.render_id else None
    script = db.get(Script, r.script_id) if r and r.script_id else None
    ctx = script_context(db, r) if r and script else None
    thumb = pub.selected_thumbnail(db, ap.project_id)
    return {"id": str(ap.id), "status": ap.status, "note": ap.note, "created_at": ap.created_at.isoformat(),
            "render": None if not r else {"id": str(r.id), "duration_seconds": r.duration_seconds, "quality": r.quality or [],
                                          "warnings": r.warnings or [], "aspect_ratio": r.aspect_ratio},
            "script_title": script.title if script else None,
            "metadata": ctx["metadata"] if ctx else {}, "accuracy_warnings": ctx["accuracy_warnings"] if ctx else [],
            "uses_ai_voice": ctx["uses_tts"] if ctx else False, "thumbnail_id": str(thumb.id) if thumb else None}


@router.get("/approvals")
def list_approvals(status_filter: str | None = None, owner: Owner = Depends(get_current_owner), db: Session = Depends(get_db)):
    q = select(Approval).join(Project, Project.id == Approval.project_id).where(Project.owner_id == owner.id)
    if status_filter:
        q = q.where(Approval.status == status_filter)
    rows = db.scalars(q.order_by(Approval.created_at.desc()).limit(40)).all()
    return [serialize_approval(db, a) for a in rows]


def _approval(approval_id: uuid.UUID, owner: Owner, db: Session) -> Approval:
    row = db.scalar(select(Approval).join(Project, Project.id == Approval.project_id)
                    .where(Approval.id == approval_id, Project.owner_id == owner.id))
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Approval not found")
    return row


class ApproveIn(BaseModel):
    account_id: uuid.UUID
    visibility: str = Field(default="private", pattern="^(private|unlisted|public)$")
    publish_at: datetime | None = None
    made_for_kids: bool
    contains_synthetic_media: bool


def _trigger(job_id, tasks: BackgroundTasks, session_factory, storage, client):
    if get_settings().job_backend == "celery":
        from app.jobs.celery_app import upload_video

        upload_video.delay(str(job_id))
    else:
        tasks.add_task(_run, session_factory, job_id, storage, client)


def _run(session_factory, job_id, storage, client):
    with session_factory() as db:
        pub.run_upload(db, job_id, storage, client)


@router.post("/approvals/{approval_id}/approve", status_code=status.HTTP_202_ACCEPTED)
def approve(approval_id: uuid.UUID, body: ApproveIn, request: Request, tasks: BackgroundTasks,
            owner: Owner = Depends(get_current_owner), db: Session = Depends(get_db),
            storage: Storage = Depends(get_storage), client: YouTubeClient = Depends(get_youtube_client),
            session_factory=Depends(get_session_factory)):
    ap = _approval(approval_id, owner, db)
    if ap.status != "pending":
        raise HTTPException(status.HTTP_409_CONFLICT, f"This approval is already {ap.status}")
    render = db.get(VideoRender, ap.render_id)
    account = db.scalar(select(YouTubeAccount).where(YouTubeAccount.id == body.account_id, YouTubeAccount.owner_id == owner.id))
    if account is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "YouTube account not found")
    try:
        job = pub.queue_upload(db, owner, render, account, visibility=body.visibility, publish_at=body.publish_at,
                               made_for_kids=body.made_for_kids, synthetic=body.contains_synthetic_media, approval=ap)
    except pub.PublishError as exc:
        raise _http(exc) from exc
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
    ap.status, ap.decided_at = "approved", datetime.now(timezone.utc)
    audit(db, owner.id, "approval.approved", request, approval_id=str(ap.id), upload_job_id=str(job.id))
    db.commit()
    _trigger(job.id, tasks, session_factory, storage, client)
    return {"upload_job_id": str(job.id), "status": job.status}


class RejectIn(BaseModel):
    note: str | None = Field(default=None, max_length=500)


@router.post("/approvals/{approval_id}/reject")
def reject(approval_id: uuid.UUID, body: RejectIn, request: Request, owner: Owner = Depends(get_current_owner),
           db: Session = Depends(get_db)):
    ap = _approval(approval_id, owner, db)
    if ap.status != "pending":
        raise HTTPException(status.HTTP_409_CONFLICT, f"This approval is already {ap.status}")
    ap.status, ap.note, ap.decided_at = "rejected", body.note, datetime.now(timezone.utc)
    audit(db, owner.id, "approval.rejected", request, approval_id=str(ap.id))
    db.commit()
    return serialize_approval(db, ap)


def serialize_job(db: Session, j: UploadJob) -> dict:
    res = (j.metadata_json or {}).get("resource", {})
    acct = db.get(YouTubeAccount, j.account_id)
    return {"id": str(j.id), "title": res.get("snippet", {}).get("title"), "status": j.status, "progress": j.progress,
            "visibility": j.visibility, "publish_at": j.publish_at.isoformat() if j.publish_at else None,
            "upload_at": j.upload_at.isoformat() if j.upload_at else None, "error": j.error, "attempts": j.attempts,
            "youtube_video_id": j.youtube_video_id,
            "youtube_url": f"https://www.youtube.com/watch?v={j.youtube_video_id}" if j.youtube_video_id else None,
            "channel": acct.channel_title if acct else None, "warnings": (j.metadata_json or {}).get("warnings", []),
            "created_at": j.created_at.isoformat()}


def _job(job_id: uuid.UUID, owner: Owner, db: Session) -> UploadJob:
    row = db.scalar(select(UploadJob).join(Project, Project.id == UploadJob.project_id)
                    .where(UploadJob.id == job_id, Project.owner_id == owner.id))
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Upload not found")
    return row


@router.get("/uploads")
def list_uploads(owner: Owner = Depends(get_current_owner), db: Session = Depends(get_db)):
    rows = db.scalars(select(UploadJob).join(Project, Project.id == UploadJob.project_id)
                      .where(Project.owner_id == owner.id).order_by(UploadJob.created_at.desc()).limit(40)).all()
    return [serialize_job(db, j) for j in rows]


@router.post("/uploads/{job_id}/retry", status_code=status.HTTP_202_ACCEPTED)
def retry_upload(job_id: uuid.UUID, tasks: BackgroundTasks, owner: Owner = Depends(get_current_owner),
                 db: Session = Depends(get_db), storage: Storage = Depends(get_storage),
                 client: YouTubeClient = Depends(get_youtube_client), session_factory=Depends(get_session_factory)):
    j = _job(job_id, owner, db)
    if j.status != "failed":
        raise HTTPException(status.HTTP_409_CONFLICT, "Only failed uploads can be retried")
    j.status, j.error = "queued", None  # keeps the saved session so the upload resumes
    db.commit()
    _trigger(j.id, tasks, session_factory, storage, client)
    return serialize_job(db, j)


@router.post("/uploads/{job_id}/cancel")
def cancel_upload(job_id: uuid.UUID, request: Request, owner: Owner = Depends(get_current_owner), db: Session = Depends(get_db)):
    j = _job(job_id, owner, db)
    if j.status not in pub.ACTIVE:
        raise HTTPException(status.HTTP_409_CONFLICT, "Only queued or uploading videos can be cancelled")
    j.status = "cancelled"
    audit(db, owner.id, "upload.cancelled", request, upload_job_id=str(j.id))
    db.commit()
    return serialize_job(db, j)


@router.get("/publishing/calendar")
def calendar(owner: Owner = Depends(get_current_owner), db: Session = Depends(get_db)):
    rows = db.scalars(select(UploadJob).join(Project, Project.id == UploadJob.project_id)
                      .where(Project.owner_id == owner.id, UploadJob.status.in_(["queued", "uploading", "scheduled", "published", "uploaded"]))
                      .order_by(UploadJob.created_at.desc()).limit(60)).all()
    items = [{**serialize_job(db, j), "when": (j.publish_at or j.upload_at or j.created_at).isoformat()} for j in rows]
    return sorted(items, key=lambda x: x["when"], reverse=True)
