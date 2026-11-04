"""Script context for publishing: metadata, chapters, accuracy warnings, whether narration is AI-generated."""
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.media.timeline import SceneInput, plan
from app.models import AudioAsset, Scene, Script, VideoRender
from app.services import metadata as meta_svc
from app.services.render_service import narration_hash

INTRO_SECONDS = 2.5


def script_context(db: Session, render: VideoRender) -> dict:
    script = db.get(Script, render.script_id)
    scenes = list(db.scalars(select(Scene).where(Scene.script_id == script.id).order_by(Scene.position)).all())
    inputs, uses_tts = [], False
    for sc in scenes:
        audio = db.scalar(select(AudioAsset).where(AudioAsset.scene_id == sc.id).order_by(AudioAsset.created_at.desc()))
        fresh = bool(audio and audio.text_hash == narration_hash(sc.narration))
        uses_tts = uses_tts or bool(fresh and audio.source == "tts")
        inputs.append(SceneInput(id=str(sc.id), position=sc.position, narration=sc.narration or "", subtitle=sc.subtitle,
                                 audio_seconds=audio.duration_seconds if fresh else None, options=sc.options or {}))
    planned = plan(inputs)
    intro = INTRO_SECONDS if (render.options or {}).get("intro_text") else 0.0
    titles = {str(sc.id): sc.title for sc in scenes if sc.title}
    meta = script.metadata_json or {}
    script_text = " ".join(sc.narration or "" for sc in scenes) + " " + script.title
    return {
        "script": script, "metadata": meta, "language": script.language, "uses_tts": uses_tts,
        "chapters_text": meta_svc.chapter_block(planned, titles, intro) if len(planned) >= 3 else "",
        "accuracy_warnings": meta_svc.accuracy_warnings(meta, script_text, []),
    }
