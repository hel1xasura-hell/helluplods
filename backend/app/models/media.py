import uuid
from datetime import datetime

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, IdMixin, TimestampMixin


class BrowserSession(IdMixin, TimestampMixin, Base):
    __tablename__ = "browser_sessions"
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    mode: Mapped[str] = mapped_column(String(16), default="cloud")
    status: Mapped[str] = mapped_column(String(24), default="created")
    current_url: Mapped[str | None] = mapped_column(String(2048))
    device_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("devices.id", ondelete="SET NULL"))


class Screenshot(IdMixin, TimestampMixin, Base):
    __tablename__ = "screenshots"
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    session_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("browser_sessions.id", ondelete="SET NULL"))
    storage_object_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("storage_objects.id"))
    url: Mapped[str | None] = mapped_column(String(2048))
    captured_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Recording(IdMixin, TimestampMixin, Base):
    __tablename__ = "recordings"
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    session_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("browser_sessions.id", ondelete="SET NULL"))
    storage_object_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("storage_objects.id"))
    duration_seconds: Mapped[float | None] = mapped_column(Float)
    is_real_capture: Mapped[bool] = mapped_column(default=True)
    executor: Mapped[str | None] = mapped_column(String(16))  # cloud|local
    source_url: Mapped[str | None] = mapped_column(String(2048))
    width: Mapped[int | None] = mapped_column(Integer)
    height: Mapped[int | None] = mapped_column(Integer)
    actions: Mapped[list] = mapped_column(JSON, default=list)


class Script(IdMixin, TimestampMixin, Base):
    __tablename__ = "scripts"
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(300))
    language: Mapped[str] = mapped_column(String(16), default="en")
    version: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(String(24), default="draft")
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)  # title, description, tags for YouTube


class Scene(IdMixin, TimestampMixin, Base):
    __tablename__ = "scenes"
    script_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("scripts.id", ondelete="CASCADE"), index=True)
    position: Mapped[int] = mapped_column(Integer)
    title: Mapped[str | None] = mapped_column(String(200))
    narration: Mapped[str] = mapped_column(Text, default="")
    subtitle: Mapped[str | None] = mapped_column(Text)
    recording_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("recordings.id", ondelete="SET NULL"))
    options: Mapped[dict] = mapped_column(JSON, default=dict)


class AudioAsset(IdMixin, TimestampMixin, Base):
    __tablename__ = "audio_assets"
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    scene_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("scenes.id", ondelete="SET NULL"))
    storage_object_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("storage_objects.id"))
    voice: Mapped[str | None] = mapped_column(String(100))
    provider: Mapped[str | None] = mapped_column(String(50))
    source: Mapped[str] = mapped_column(String(16), default="tts")  # tts|upload
    duration_seconds: Mapped[float | None] = mapped_column(Float)
    text_hash: Mapped[str | None] = mapped_column(String(64))  # hash of the narration this audio was made for


class VideoAsset(IdMixin, TimestampMixin, Base):
    __tablename__ = "video_assets"
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    storage_object_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("storage_objects.id"))
    kind: Mapped[str] = mapped_column(String(24), default="render")


class Thumbnail(IdMixin, TimestampMixin, Base):
    __tablename__ = "thumbnails"
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    storage_object_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("storage_objects.id"))
    text: Mapped[str | None] = mapped_column(String(200))
    template: Mapped[str | None] = mapped_column(String(24))
    accent: Mapped[str | None] = mapped_column(String(7))
    selected: Mapped[bool] = mapped_column(default=False)


class VideoRender(IdMixin, TimestampMixin, Base):
    __tablename__ = "video_renders"
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    script_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("scripts.id", ondelete="SET NULL"))
    status: Mapped[str] = mapped_column(String(24), default="queued")
    aspect_ratio: Mapped[str] = mapped_column(String(8), default="16:9")
    width: Mapped[int] = mapped_column(Integer, default=1920)
    height: Mapped[int] = mapped_column(Integer, default=1080)
    fps: Mapped[int] = mapped_column(Integer, default=30)
    progress: Mapped[float] = mapped_column(Float, default=0.0)
    error: Mapped[str | None] = mapped_column(Text)
    options: Mapped[dict] = mapped_column(JSON, default=dict)
    quality: Mapped[list] = mapped_column(JSON, default=list)
    warnings: Mapped[list] = mapped_column(JSON, default=list)
    srt: Mapped[str | None] = mapped_column(Text)
    duration_seconds: Mapped[float | None] = mapped_column(Float)
    cancel_requested: Mapped[bool] = mapped_column(default=False)
    video_asset_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("video_assets.id"))
