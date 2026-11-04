"""Turn a script into a rendered video: resolve real footage + narration, run FFmpeg, store, quality-check."""
import hashlib
import tempfile
import uuid
from collections.abc import Callable
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.media.ffmpeg_render import (
    RenderCancelled, RenderError, RenderResult, RenderSettings, quality_check, render,
)
from app.media.timeline import SceneInput
from app.models import (
    AudioAsset, Notification, Project, Recording, Scene, Script, StorageObject, VideoAsset, VideoRender,
)
from app.services.storage import Storage

Renderer = Callable[..., RenderResult]


def narration_hash(text: str) -> str:
    return hashlib.sha256(" ".join((text or "").split()).encode()).hexdigest()


def settings_from_options(opts: dict) -> RenderSettings:
    allowed = {f for f in RenderSettings.__dataclass_fields__ if f not in {"font_path", "music_path"}}
    return RenderSettings(**{k: v for k, v in opts.items() if k in allowed})


def build_scene_inputs(db: Session, script: Script, storage: Storage, work: Path) -> tuple[list[SceneInput], list[str]]:
    """Resolve each scene's real recording and its up-to-date narration audio into local files."""
    inputs, notes = [], []
    scenes = db.scalars(select(Scene).where(Scene.script_id == script.id).order_by(Scene.position)).all()
    for sc in scenes:
        footage_path, f_secs, actions, size = None, None, [], None
        if sc.recording_id:
            rec = db.get(Recording, sc.recording_id)
            if rec and rec.is_real_capture and rec.storage_object_id:
                obj = db.get(StorageObject, rec.storage_object_id)
                footage_path = work / f"footage_{rec.id}.webm"
                if not footage_path.exists():
                    footage_path.write_bytes(storage.get(obj.key))
                f_secs, actions = rec.duration_seconds, rec.actions or []
                size = (rec.width or 1280, rec.height or 720)
        audio_path, a_secs = None, None
        audio = db.scalar(select(AudioAsset).where(AudioAsset.scene_id == sc.id).order_by(AudioAsset.created_at.desc()))
        if audio and audio.storage_object_id:
            if audio.text_hash == narration_hash(sc.narration):
                obj = db.get(StorageObject, audio.storage_object_id)
                audio_path = work / f"audio_{audio.id}"
                audio_path.write_bytes(storage.get(obj.key))
                a_secs = audio.duration_seconds
            else:
                notes.append(f"Scene {sc.position}: narration changed since its audio was made, so the audio was not used.")
        inputs.append(SceneInput(
            id=str(sc.id), position=sc.position, narration=sc.narration or "", subtitle=sc.subtitle,
            audio_path=str(audio_path) if audio_path else None, audio_seconds=a_secs,
            footage_path=str(footage_path) if footage_path else None, footage_seconds=f_secs,
            footage_actions=actions, footage_size=size, options=sc.options or {}))
    return inputs, notes


def run_render(db: Session, render_id: uuid.UUID, storage: Storage, renderer: Renderer | None = None,
               checker: Callable | None = None) -> uuid.UUID | None:
    """Returns the id of an upload job queued by automatic publishing, if any."""
    job = db.get(VideoRender, render_id)
    if job is None or job.status != "queued":
        return None
    project = db.get(Project, job.project_id)
    script = db.get(Script, job.script_id)
    job.status, job.progress = "rendering", 0.0
    db.commit()

    def stop() -> bool:
        db.refresh(job)
        return job.cancel_requested

    def progress(p: float) -> None:
        job.progress = round(p, 3)
        db.commit()

    renderer = renderer or render
    try:
        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp)
            scenes, notes = build_scene_inputs(db, script, storage, work)
            st = settings_from_options(job.options)
            out = work / "final.mp4"
            result = renderer(scenes, st, out, progress=progress, should_stop=stop, workdir=work / "steps")
            checks = (checker or quality_check)(result, st, scenes)
            data = out.read_bytes()
        key = f"{project.owner_id}/{project.id}/renders/{uuid.uuid4()}.mp4"
        meta = storage.put(key, data, "video/mp4")
        obj = StorageObject(owner_id=project.owner_id, backend=storage.backend, key=key, content_type="video/mp4",
                            size_bytes=meta["size_bytes"], sha256=meta["sha256"])
        db.add(obj)
        db.flush()
        asset = VideoAsset(project_id=project.id, storage_object_id=obj.id, kind="render")
        db.add(asset)
        db.flush()
        job.video_asset_id, job.srt, job.duration_seconds = asset.id, result.srt, result.duration
        job.quality = checks
        job.warnings = notes + result.warnings
        failed = [c for c in checks if c["status"] == "fail"]
        job.status, job.progress = ("failed" if failed else "ready"), 1.0
        job.error = "; ".join(c["detail"] for c in failed) or None
        title = "Video ready for review" if not failed else "Video failed quality checks"
    except RenderCancelled:
        job.status, job.error = "cancelled", "Cancelled by the owner"
        title = "Render cancelled"
    except RenderError as exc:
        job.status, job.error = "failed", str(exc)[:500]
        title = "Render failed"
    except Exception as exc:
        job.status, job.error = "failed", f"{type(exc).__name__}: {exc}"[:500]
        title = "Render failed"
    db.add(Notification(owner_id=project.owner_id, kind="render", title=title, body=(job.error or script.title)[:300]))
    db.commit()
    if job.status == "ready":
        from app.services.publishing import after_render

        upload = after_render(db, job)
        db.commit()
        return upload.id if upload else None
    return None
