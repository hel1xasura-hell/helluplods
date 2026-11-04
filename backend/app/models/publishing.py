import uuid
from datetime import date, datetime

from sqlalchemy import JSON, Date, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, IdMixin, TimestampMixin


class Approval(IdMixin, TimestampMixin, Base):
    __tablename__ = "approvals"
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    render_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("video_renders.id", ondelete="SET NULL"))
    status: Mapped[str] = mapped_column(String(16), default="pending")  # pending|approved|rejected
    note: Mapped[str | None] = mapped_column(Text)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class YouTubeAccount(IdMixin, TimestampMixin, Base):
    __tablename__ = "youtube_accounts"
    owner_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("owners.id", ondelete="CASCADE"), index=True)
    channel_id: Mapped[str] = mapped_column(String(64))
    channel_title: Mapped[str | None] = mapped_column(String(200))
    refresh_token_encrypted: Mapped[str] = mapped_column(Text)
    quota_used_today: Mapped[int] = mapped_column(default=0)
    quota_day: Mapped[date | None] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(16), default="connected")
    __table_args__ = (UniqueConstraint("owner_id", "channel_id", name="uq_yt_owner_channel"),)


class UploadJob(IdMixin, TimestampMixin, Base):
    __tablename__ = "upload_jobs"
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    render_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("video_renders.id"))
    account_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("youtube_accounts.id"))
    status: Mapped[str] = mapped_column(String(24), default="queued")
    visibility: Mapped[str] = mapped_column(String(16), default="private")
    youtube_video_id: Mapped[str | None] = mapped_column(String(32))
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)
    error: Mapped[str | None] = mapped_column(Text)
    progress: Mapped[float] = mapped_column(Float, default=0.0)
    bytes_uploaded: Mapped[int] = mapped_column(Integer, default=0)
    session_uri_encrypted: Mapped[str | None] = mapped_column(Text)
    upload_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    publish_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    approval_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("approvals.id", ondelete="SET NULL"))
    # Duplicate-upload protection: one job per render per account.
    __table_args__ = (UniqueConstraint("render_id", "account_id", name="uq_upload_render_account"),)


class PublishingSchedule(IdMixin, TimestampMixin, Base):
    __tablename__ = "publishing_schedules"
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    upload_job_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("upload_jobs.id", ondelete="SET NULL"))
    publish_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class AnalyticsSnapshot(IdMixin, TimestampMixin, Base):
    __tablename__ = "analytics"
    project_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("projects.id", ondelete="SET NULL"))
    youtube_video_id: Mapped[str | None] = mapped_column(String(32), index=True)
    metrics: Mapped[dict] = mapped_column(JSON, default=dict)
