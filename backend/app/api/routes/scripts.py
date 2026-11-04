import asyncio
import tempfile
import uuid
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.routes.research import get_session_factory
from app.auth.deps import audit, get_current_owner, get_owned_project
from app.core.config import get_settings
from app.db.session import get_db
from app.media import tts
from app.media.ffmpeg_render import RenderError, probe
from app.media.subtitles import cues_for_scene, to_srt, to_vtt
from app.media.timeline import SceneInput, plan
from app.models import (
    AudioAsset, Owner, Project, Recording, ResearchReport, ResearchTarget, Scene, Script, StorageObject,
)
from app.services import metadata as meta_svc
from app.services.ai import AINotConfigured, AIProvider, get_ai_provider
from app.services.render_service import narration_hash
from app.services.script_ai import draft_scenes
from app.services.storage import Storage, get_storage

router = APIRouter(prefix="/api", tags=["scripts"])
MAX_AUDIO_BYTES = 50 * 1024 * 1024


def get_ai() -> AIProvider:
    try:
        return get_ai_provider()
    except AINotConfigured as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE,
                            f"{exc} Write the scenes yourself, or add the key to enable AI drafting.") from exc


def get_tts_providers():
    return tts.providers(get_settings())


def _script(script_id: uuid.UUID, owner: Owner, db: Session) -> Script:
    row = db.scalar(select(Script).join(Project, Project.id == Script.project_id)
                    .where(Script.id == script_id, Project.owner_id == owner.id))
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Script not found")
    return row


def _scene(scene_id: uuid.UUID, owner: Owner, db: Session) -> Scene:
    row = db.scalar(select(Scene).join(Script, Script.id == Scene.script_id)
                    .join(Project, Project.id == Script.project_id).where(Scene.id == scene_id, Project.owner_id == owner.id))
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Scene not found")
    return row


def _scenes(db: Session, script_id) -> list[Scene]:
    return list(db.scalars(select(Scene).where(Scene.script_id == script_id).order_by(Scene.position)).all())


def _latest_audio(db: Session, scene: Scene) -> AudioAsset | None:
    return db.scalar(select(AudioAsset).where(AudioAsset.scene_id == scene.id).order_by(AudioAsset.created_at.desc()))


def serialize_scene(db: Session, sc: Scene) -> dict:
    audio = _latest_audio(db, sc)
    fresh = bool(audio and audio.text_hash == narration_hash(sc.narration))
    return {"id": str(sc.id), "position": sc.position, "title": sc.title, "narration": sc.narration,
            "subtitle": sc.subtitle, "recording_id": str(sc.recording_id) if sc.recording_id else None,
            "options": sc.options or {}, "audio": None if not audio else
            {"source": audio.source, "provider": audio.provider, "duration_seconds": audio.duration_seconds, "up_to_date": fresh}}


def serialize_script(db: Session, s: Script) -> dict:
    return {"id": str(s.id), "project_id": str(s.project_id), "title": s.title, "language": s.language,
            "status": s.status, "metadata": s.metadata_json or {}, "scenes": [serialize_scene(db, x) for x in _scenes(db, s.id)]}


class ScriptCreate(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    language: str = Field(default="en", pattern=r"^[a-z]{2}(-[A-Za-z]{2})?$")
    from_target_id: uuid.UUID | None = None


class ScriptPatch(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=300)
    language: str | None = Field(default=None, pattern=r"^[a-z]{2}(-[A-Za-z]{2})?$")


class SceneIn(BaseModel):
    title: str | None = Field(default=None, max_length=200)
    narration: str = Field(default="", max_length=3000)
    subtitle: str | None = Field(default=None, max_length=3000)
    recording_id: uuid.UUID | None = None
    options: dict | None = None

    @field_validator("options")
    @classmethod
    def check_options(cls, v):
        if v is None:
            return v
        unknown = set(v) - {"trim_start", "min_seconds", "zoom"}
        if unknown:
            raise ValueError(f"Unknown options: {sorted(unknown)}")
        if not 0 <= float(v.get("trim_start", 0) or 0) <= 3600:
            raise ValueError("trim_start must be between 0 and 3600 seconds")
        if not 0 <= float(v.get("min_seconds", 0) or 0) <= 120:
            raise ValueError("min_seconds must be between 0 and 120")
        z = v.get("zoom")
        if z is not None and not (1.0 <= float(z.get("factor", 1.4)) <= 3.0 and 0 <= float(z.get("cx", .5)) <= 1 and 0 <= float(z.get("cy", .5)) <= 1):
            raise ValueError("zoom needs factor 1-3 and cx/cy between 0 and 1")
        return v


def _check_recording(db: Session, owner: Owner, project_id, recording_id) -> None:
    if recording_id is None:
        return
    ok = db.scalar(select(Recording.id).join(Project, Project.id == Recording.project_id)
                   .where(Recording.id == recording_id, Project.owner_id == owner.id, Project.id == project_id))
    if ok is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "That recording doesn't belong to this project")


@router.get("/projects/{project_id}/scripts")
def list_scripts(project_id: uuid.UUID, owner: Owner = Depends(get_current_owner), db: Session = Depends(get_db)):
    get_owned_project(project_id, owner, db)
    rows = db.scalars(select(Script).where(Script.project_id == project_id).order_by(Script.created_at.desc())).all()
    return [{"id": str(s.id), "title": s.title, "language": s.language, "status": s.status,
             "scene_count": db.scalar(select(func.count()).select_from(Scene).where(Scene.script_id == s.id))} for s in rows]


@router.post("/projects/{project_id}/scripts", status_code=status.HTTP_201_CREATED)
def create_script(project_id: uuid.UUID, body: ScriptCreate, request: Request,
                  owner: Owner = Depends(get_current_owner), db: Session = Depends(get_db)):
    get_owned_project(project_id, owner, db)
    script = Script(project_id=project_id, title=body.title, language=body.language)
    db.add(script)
    db.flush()
    if body.from_target_id:
        report = db.scalar(select(ResearchReport).join(ResearchTarget, ResearchTarget.id == ResearchReport.target_id)
                           .where(ResearchTarget.id == body.from_target_id, ResearchTarget.project_id == project_id)
                           .order_by(ResearchReport.created_at.desc()))
        if report is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "No research report for that target")
        # Skeleton only: titles from observed headings, narration left empty for the owner (or AI draft) to write.
        for i, f in enumerate(report.body.get("features", [])[:6], 1):
            db.add(Scene(script_id=script.id, position=i, title=f["name"][:200], narration=""))
    audit(db, owner.id, "script.created", request, script_id=str(script.id))
    db.commit()
    return serialize_script(db, script)


@router.get("/scripts/{script_id}")
def get_script(script_id: uuid.UUID, owner: Owner = Depends(get_current_owner), db: Session = Depends(get_db)):
    return serialize_script(db, _script(script_id, owner, db))


@router.patch("/scripts/{script_id}")
def patch_script(script_id: uuid.UUID, body: ScriptPatch, owner: Owner = Depends(get_current_owner),
                 db: Session = Depends(get_db)):
    s = _script(script_id, owner, db)
    for k, v in body.model_dump(exclude_none=True).items():
        setattr(s, k, v)
    db.commit()
    return serialize_script(db, s)


@router.delete("/scripts/{script_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_script(script_id: uuid.UUID, request: Request, owner: Owner = Depends(get_current_owner),
                  db: Session = Depends(get_db)):
    s = _script(script_id, owner, db)
    audit(db, owner.id, "script.deleted", request, script_id=str(s.id))
    for sc in _scenes(db, s.id):
        for a in db.scalars(select(AudioAsset).where(AudioAsset.scene_id == sc.id)).all():
            db.delete(a)
        db.delete(sc)
    db.delete(s)
    db.commit()


@router.post("/scripts/{script_id}/scenes", status_code=status.HTTP_201_CREATED)
def add_scene(script_id: uuid.UUID, body: SceneIn, owner: Owner = Depends(get_current_owner), db: Session = Depends(get_db)):
    s = _script(script_id, owner, db)
    _check_recording(db, owner, s.project_id, body.recording_id)
    pos = (db.scalar(select(func.max(Scene.position)).where(Scene.script_id == s.id)) or 0) + 1
    sc = Scene(script_id=s.id, position=pos, **body.model_dump(exclude_none=True))
    db.add(sc)
    db.commit()
    return serialize_scene(db, sc)


@router.patch("/scenes/{scene_id}")
def patch_scene(scene_id: uuid.UUID, body: SceneIn, owner: Owner = Depends(get_current_owner), db: Session = Depends(get_db)):
    sc = _scene(scene_id, owner, db)
    project_id = db.get(Script, sc.script_id).project_id
    fields = body.model_dump(exclude_unset=True)
    if "options" in fields and fields["options"] is None:
        fields["options"] = {}  # the column is NOT NULL; null means "clear the options"
    if "recording_id" in fields:
        _check_recording(db, owner, project_id, fields["recording_id"])
    for k, v in fields.items():
        setattr(sc, k, v)
    db.commit()
    return serialize_scene(db, sc)


@router.delete("/scenes/{scene_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_scene(scene_id: uuid.UUID, owner: Owner = Depends(get_current_owner), db: Session = Depends(get_db)):
    sc = _scene(scene_id, owner, db)
    script_id = sc.script_id
    for a in db.scalars(select(AudioAsset).where(AudioAsset.scene_id == sc.id)).all():
        db.delete(a)
    db.delete(sc)
    db.flush()
    for i, rest in enumerate(_scenes(db, script_id), 1):
        rest.position = i
    db.commit()


class Reorder(BaseModel):
    order: list[uuid.UUID]


@router.post("/scripts/{script_id}/scenes/reorder")
def reorder(script_id: uuid.UUID, body: Reorder, owner: Owner = Depends(get_current_owner), db: Session = Depends(get_db)):
    s = _script(script_id, owner, db)
    scenes = {sc.id: sc for sc in _scenes(db, s.id)}
    if set(body.order) != set(scenes) or len(body.order) != len(scenes):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Order must list every scene exactly once")
    for i, sid in enumerate(body.order, 1):
        scenes[sid].position = i
    db.commit()
    return serialize_script(db, s)


# ---------- AI draft ----------
@router.post("/scripts/{script_id}/generate-ai")
def generate_with_ai(script_id: uuid.UUID, target_id: uuid.UUID, owner: Owner = Depends(get_current_owner),
                     db: Session = Depends(get_db), ai=Depends(get_ai)):
    s = _script(script_id, owner, db)
    report = db.scalar(select(ResearchReport).join(ResearchTarget, ResearchTarget.id == ResearchReport.target_id)
                       .where(ResearchTarget.id == target_id, ResearchTarget.project_id == s.project_id)
                       .order_by(ResearchReport.created_at.desc()))
    if report is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No research report for that target")
    scenes = asyncio.run(draft_scenes(ai, report.body))
    if not scenes:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "The AI did not return usable scenes. Nothing was changed.")
    start = (db.scalar(select(func.max(Scene.position)).where(Scene.script_id == s.id)) or 0)
    for i, sc in enumerate(scenes, 1):
        db.add(Scene(script_id=s.id, position=start + i, title=sc["title"], narration=sc["narration"]))
    db.commit()
    return serialize_script(db, s)


# ---------- timeline, subtitles, chapters ----------
def _planned(db: Session, s: Script):
    inputs = []
    for sc in _scenes(db, s.id):
        a = _latest_audio(db, sc)
        fresh = a and a.text_hash == narration_hash(sc.narration)
        inputs.append(SceneInput(id=str(sc.id), position=sc.position, narration=sc.narration or "", subtitle=sc.subtitle,
                                 audio_seconds=a.duration_seconds if fresh else None, options=sc.options or {}))
    return plan(inputs)


@router.get("/scripts/{script_id}/subtitles.{fmt}")
def subtitles(script_id: uuid.UUID, fmt: str, owner: Owner = Depends(get_current_owner), db: Session = Depends(get_db)):
    if fmt not in {"srt", "vtt"}:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Use .srt or .vtt")
    s = _script(script_id, owner, db)
    cues = []
    for p in _planned(db, s):
        text = p.scene.subtitle if p.scene.subtitle is not None else p.scene.narration
        cues += cues_for_scene(text, p.start, p.start + p.duration - 0.2)
    body = to_srt(cues) if fmt == "srt" else to_vtt(cues)
    return Response(body, media_type="text/plain; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="subtitles.{fmt}"'})


class MetaIn(BaseModel):
    title: str = Field(default="", max_length=200)
    description: str = Field(default="", max_length=10000)
    tags: list[str] = Field(default_factory=list, max_length=60)
    hashtags: list[str] = Field(default_factory=list, max_length=15)
    intro_seconds: float = Field(default=0.0, ge=0, le=30)


@router.get("/scripts/{script_id}/metadata")
def get_metadata(script_id: uuid.UUID, intro_seconds: float = 0.0, owner: Owner = Depends(get_current_owner),
                 db: Session = Depends(get_db)):
    from app.media.timeline import chapters

    s = _script(script_id, owner, db)
    planned = _planned(db, s)
    titles = {str(sc.id): sc.title for sc in _scenes(db, s.id) if sc.title}
    ch = chapters(planned, titles, intro_seconds)
    warns = []
    if len(ch) < 3:
        warns.append("YouTube chapters need at least 3 entries")
    if any(b["start"] - a["start"] < 10 for a, b in zip(ch, ch[1:])):
        warns.append("YouTube chapters must each be at least 10 seconds long")
    meta = s.metadata_json or {}
    script_text = " ".join(sc.narration or "" for sc in _scenes(db, s.id)) + " " + s.title
    return {"metadata": meta, "chapters": ch, "chapters_text": meta_svc.chapter_block(planned, titles, intro_seconds),
            "chapter_warnings": warns, "accuracy_warnings": meta_svc.accuracy_warnings(meta, script_text, [])}


@router.put("/scripts/{script_id}/metadata")
def put_metadata(script_id: uuid.UUID, body: MetaIn, owner: Owner = Depends(get_current_owner), db: Session = Depends(get_db)):
    s = _script(script_id, owner, db)
    errs = meta_svc.validate_metadata(body.model_dump())
    if errs:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "; ".join(errs))
    s.metadata_json = body.model_dump()
    db.commit()
    return {"metadata": s.metadata_json}


# ---------- narration audio ----------
def _store_audio(db: Session, project: Project, storage: Storage, scene: Scene, data: bytes, ext: str,
                 source: str, provider: str | None, duration: float | None) -> AudioAsset:
    key = f"{project.owner_id}/{project.id}/audio/{uuid.uuid4()}{ext}"
    meta = storage.put(key, data, "audio/mpeg")
    obj = StorageObject(owner_id=project.owner_id, backend=storage.backend, key=key, content_type="audio/mpeg",
                        size_bytes=meta["size_bytes"], sha256=meta["sha256"])
    db.add(obj)
    db.flush()
    a = AudioAsset(project_id=project.id, scene_id=scene.id, storage_object_id=obj.id, provider=provider,
                   source=source, duration_seconds=duration, text_hash=narration_hash(scene.narration))
    db.add(a)
    db.flush()
    return a


@router.put("/scenes/{scene_id}/audio")
async def upload_audio(scene_id: uuid.UUID, request: Request, owner: Owner = Depends(get_current_owner),
                       db: Session = Depends(get_db), storage: Storage = Depends(get_storage)):
    """Your own narration recording for this scene."""
    sc = _scene(scene_id, owner, db)
    data = await request.body()
    if not data or len(data) > MAX_AUDIO_BYTES:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Audio is empty or larger than 50 MB")
    ext = tts.looks_like_audio(data[:16])
    if ext is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "File is not WAV, MP3, OGG, M4A or WebM audio")
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / f"in{ext}"
        path.write_bytes(data)
        try:
            info = probe(path)
            duration = float(info["format"]["duration"])
        except (RenderError, KeyError, ValueError) as exc:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Couldn't read that audio file") from exc
    project = db.get(Project, db.get(Script, sc.script_id).project_id)
    _store_audio(db, project, storage, sc, data, ext, "upload", None, round(duration, 2))
    db.commit()
    return serialize_scene(db, sc)


@router.get("/scenes/{scene_id}/audio")
def get_audio(scene_id: uuid.UUID, owner: Owner = Depends(get_current_owner), db: Session = Depends(get_db),
              storage: Storage = Depends(get_storage)):
    sc = _scene(scene_id, owner, db)
    a = _latest_audio(db, sc)
    if a is None or a.storage_object_id is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No audio for this scene")
    obj = db.get(StorageObject, a.storage_object_id)
    data = storage.get(obj.key)
    return Response(data, media_type="audio/mpeg", headers={"X-Content-Type-Options": "nosniff"})


@router.get("/voices")
def voices(_: Owner = Depends(get_current_owner)):
    return tts.provider_status(get_settings())


class VoiceIn(BaseModel):
    provider: str = Field(pattern="^(piper|elevenlabs)$")


def _voice_job(session_factory, script_id, provider_name, storage, providers):
    with session_factory() as db:
        s = db.get(Script, script_id)
        project = db.get(Project, s.project_id)
        provider = providers[provider_name]
        for sc in _scenes(db, s.id):
            if not (sc.narration or "").strip():
                continue
            a = _latest_audio(db, sc)
            if a and a.text_hash == narration_hash(sc.narration):
                continue
            with tempfile.TemporaryDirectory() as tmp:
                out = Path(tmp) / f"scene{provider.extension}"
                try:
                    asyncio.run(provider.synthesize(sc.narration, out))
                    duration = round(float(probe(out)["format"]["duration"]), 2)
                    _store_audio(db, project, storage, sc, out.read_bytes(), provider.extension, "tts", provider_name, duration)
                    db.commit()
                except Exception:
                    db.rollback()


@router.post("/scripts/{script_id}/voice", status_code=status.HTTP_202_ACCEPTED)
def generate_voice(script_id: uuid.UUID, body: VoiceIn, tasks: BackgroundTasks, owner: Owner = Depends(get_current_owner),
                   db: Session = Depends(get_db), storage: Storage = Depends(get_storage),
                   providers=Depends(get_tts_providers), session_factory=Depends(get_session_factory)):
    s = _script(script_id, owner, db)
    missing = providers[body.provider].missing()
    if missing:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE,
                            f"{body.provider} is not configured (missing {', '.join(missing)}). "
                            "You can upload your own narration audio for each scene instead.")
    tasks.add_task(_voice_job, session_factory, s.id, body.provider, storage, providers)
    return {"status": "started"}
