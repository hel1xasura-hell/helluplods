import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException, Request, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.routes.research import get_session_factory
from app.api.routes.scripts import _script
from app.api.routes.youtube import get_youtube_client
from app.integrations.youtube_client import YouTubeClient
from app.auth.deps import audit, get_current_owner
from app.core.config import get_settings
from app.db.session import get_db
from app.media.ffmpeg_render import RenderError, RenderSettings
from app.models import Owner, Project, Scene, StorageObject, VideoAsset, VideoRender
from app.services.render_service import run_render, settings_from_options
from app.services.storage import Storage, get_storage

router = APIRouter(prefix="/api", tags=["renders"])


def get_render_hooks():
    return None, None  # (renderer, checker); tests override with fakes


class RenderIn(BaseModel):
    aspect_ratio: str = Field(default="16:9", pattern=r"^(16:9|9:16|1:1)$")
    width: int | None = Field(default=None, ge=320, le=3840)
    height: int | None = Field(default=None, ge=320, le=3840)
    fps: int = Field(default=30, ge=12, le=60)
    burn_subtitles: bool = False
    intro_text: str | None = Field(default=None, max_length=120)
    outro_text: str | None = Field(default=None, max_length=120)
    cursor_highlight: bool = True
    accent: str = Field(default="#8d6bff", pattern=r"^#[0-9a-fA-F]{6}$")
    crf: int = Field(default=20, ge=10, le=35)


def _bg(session_factory, render_id, storage, hooks, yt):
    with session_factory() as db:
        upload_id = run_render(db, render_id, storage, *hooks)
        if upload_id:  # automatic publishing queued an upload: start it now
            from app.services.publishing import run_upload

            run_upload(db, upload_id, storage, yt)


def serialize(r: VideoRender) -> dict:
    return {"id": str(r.id), "script_id": str(r.script_id) if r.script_id else None, "status": r.status,
            "progress": r.progress, "aspect_ratio": r.aspect_ratio, "width": r.width, "height": r.height, "fps": r.fps,
            "duration_seconds": r.duration_seconds, "quality": r.quality or [], "warnings": r.warnings or [],
            "error": r.error, "has_file": r.video_asset_id is not None, "created_at": r.created_at.isoformat(),
            "options": r.options or {}}


@router.post("/scripts/{script_id}/render", status_code=status.HTTP_202_ACCEPTED)
def start_render(script_id: uuid.UUID, body: RenderIn, request: Request, tasks: BackgroundTasks,
                 owner: Owner = Depends(get_current_owner), db: Session = Depends(get_db),
                 storage: Storage = Depends(get_storage), hooks=Depends(get_render_hooks),
                 yt: YouTubeClient = Depends(get_youtube_client), session_factory=Depends(get_session_factory)):
    script = _script(script_id, owner, db)
    if not db.scalar(select(func.count()).select_from(Scene).where(Scene.script_id == script.id)):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Add at least one scene before rendering")
    if db.scalar(select(VideoRender.id).where(VideoRender.script_id == script.id,
                                              VideoRender.status.in_(["queued", "rendering"]))):
        raise HTTPException(status.HTTP_409_CONFLICT, "This script is already rendering")
    opts = body.model_dump(exclude_none=True)
    try:
        st: RenderSettings = settings_from_options(opts)
        st.validate()
    except (RenderError, TypeError) as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
    w, h = st.size()
    job = VideoRender(project_id=script.project_id, script_id=script.id, status="queued", aspect_ratio=st.aspect_ratio,
                      width=w, height=h, fps=st.fps, options=opts)
    db.add(job)
    db.flush()
    audit(db, owner.id, "render.requested", request, render_id=str(job.id))
    db.commit()
    if get_settings().job_backend == "celery":
        from app.jobs.celery_app import render_video

        render_video.apply_async(args=[str(job.id)], queue="render")
    else:
        tasks.add_task(_bg, session_factory, job.id, storage, hooks, yt)
    return serialize(job)


def _job(render_id: uuid.UUID, owner: Owner, db: Session) -> VideoRender:
    row = db.scalar(select(VideoRender).join(Project, Project.id == VideoRender.project_id)
                    .where(VideoRender.id == render_id, Project.owner_id == owner.id))
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Render not found")
    return row


@router.get("/renders")
def list_renders(owner: Owner = Depends(get_current_owner), db: Session = Depends(get_db)):
    rows = db.scalars(select(VideoRender).join(Project, Project.id == VideoRender.project_id)
                      .where(Project.owner_id == owner.id).order_by(VideoRender.created_at.desc()).limit(30)).all()
    return [serialize(r) for r in rows]


@router.get("/renders/{render_id}")
def get_render(render_id: uuid.UUID, owner: Owner = Depends(get_current_owner), db: Session = Depends(get_db)):
    return serialize(_job(render_id, owner, db))


@router.post("/renders/{render_id}/cancel")
def cancel_render(render_id: uuid.UUID, request: Request, owner: Owner = Depends(get_current_owner), db: Session = Depends(get_db)):
    r = _job(render_id, owner, db)
    if r.status not in {"queued", "rendering"}:
        raise HTTPException(status.HTTP_409_CONFLICT, "This render has already finished")
    r.cancel_requested = True
    if r.status == "queued":
        r.status = "cancelled"
    audit(db, owner.id, "render.cancel_requested", request, render_id=str(r.id))
    db.commit()
    return serialize(r)


@router.get("/renders/{render_id}/subtitles.{fmt}")
def render_subtitles(render_id: uuid.UUID, fmt: str, owner: Owner = Depends(get_current_owner), db: Session = Depends(get_db)):
    from app.media.subtitles import parse_srt, to_vtt

    r = _job(render_id, owner, db)
    if not r.srt:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No subtitles for this render")
    if fmt not in {"srt", "vtt"}:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Use .srt or .vtt")
    body = r.srt if fmt == "srt" else to_vtt(parse_srt(r.srt))
    return Response(body, media_type="text/plain; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="subtitles.{fmt}"'})


@router.get("/renders/{render_id}/file")
def render_file(render_id: uuid.UUID, range: str | None = Header(default=None),
                owner: Owner = Depends(get_current_owner), db: Session = Depends(get_db),
                storage: Storage = Depends(get_storage)):
    r = _job(render_id, owner, db)
    if not r.video_asset_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "This render has no video file")
    asset = db.get(VideoAsset, r.video_asset_id)
    data = storage.get(db.get(StorageObject, asset.storage_object_id).key)
    total, headers = len(data), {"Accept-Ranges": "bytes", "X-Content-Type-Options": "nosniff"}
    if range and range.startswith("bytes="):
        try:
            a, _, b = range[6:].partition("-")
            start = int(a) if a else max(0, total - int(b))
            end = min(int(b), total - 1) if (b and a) else total - 1
            if start > end or start >= total:
                raise ValueError
        except ValueError:
            return Response(status_code=416, headers={"Content-Range": f"bytes */{total}"})
        headers["Content-Range"] = f"bytes {start}-{end}/{total}"
        return Response(data[start:end + 1], status_code=206, media_type="video/mp4", headers=headers)
    return Response(data, media_type="video/mp4", headers=headers)
