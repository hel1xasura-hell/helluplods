import uuid
from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, IdMixin, TimestampMixin


class AIAgent(IdMixin, TimestampMixin, Base):
    __tablename__ = "ai_agents"
    key: Mapped[str] = mapped_column(String(64), unique=True)
    name: Mapped[str] = mapped_column(String(120))
    enabled: Mapped[bool] = mapped_column(default=True)
    config: Mapped[dict] = mapped_column(JSON, default=dict)


class AgentRun(IdMixin, TimestampMixin, Base):
    __tablename__ = "agent_runs"
    __table_args__ = (Index("ix_agent_runs_status", "status"),)
    project_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    agent_key: Mapped[str] = mapped_column(String(64), index=True)
    status: Mapped[str] = mapped_column(String(24), default="queued")
    attempt: Mapped[int] = mapped_column(Integer, default=1)
    progress: Mapped[float] = mapped_column(default=0.0)
    input: Mapped[dict] = mapped_column(JSON, default=dict)
    output: Mapped[dict | None] = mapped_column(JSON)
    logs: Mapped[list] = mapped_column(JSON, default=list)
    error: Mapped[str | None] = mapped_column(Text)
    control: Mapped[str | None] = mapped_column(String(16))  # pause|stop requested by the owner
    current_url: Mapped[str | None] = mapped_column(String(2048))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Device(IdMixin, TimestampMixin, Base):
    """Local desktop companions. Credential is stored hashed and is revocable."""
    __tablename__ = "devices"
    owner_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("owners.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    platform: Mapped[str] = mapped_column(String(24))
    credential_hash: Mapped[str | None] = mapped_column(String(128))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Notification(IdMixin, TimestampMixin, Base):
    __tablename__ = "notifications"
    owner_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("owners.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(32))
    title: Mapped[str] = mapped_column(String(200))
    body: Mapped[str | None] = mapped_column(Text)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AuditEvent(IdMixin, TimestampMixin, Base):
    __tablename__ = "audit_events"
    owner_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("owners.id", ondelete="SET NULL"), index=True)
    action: Mapped[str] = mapped_column(String(80), index=True)
    target_type: Mapped[str | None] = mapped_column(String(48))
    target_id: Mapped[str | None] = mapped_column(String(64))
    ip: Mapped[str | None] = mapped_column(String(64))
    detail: Mapped[dict] = mapped_column(JSON, default=dict)


class APIIntegration(IdMixin, TimestampMixin, Base):
    __tablename__ = "api_integrations"
    key: Mapped[str] = mapped_column(String(48), unique=True)
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_status: Mapped[str | None] = mapped_column(String(24))


class StorageObject(IdMixin, TimestampMixin, Base):
    __tablename__ = "storage_objects"
    __table_args__ = (UniqueConstraint("backend", "key", name="uq_storage_backend_key"),)
    owner_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("owners.id", ondelete="CASCADE"), index=True)
    backend: Mapped[str] = mapped_column(String(16))  # local|s3
    key: Mapped[str] = mapped_column(String(1024))
    content_type: Mapped[str | None] = mapped_column(String(120))
    size_bytes: Mapped[int] = mapped_column(default=0)
    sha256: Mapped[str | None] = mapped_column(String(64))


class DevicePairingCode(IdMixin, TimestampMixin, Base):
    """Short-lived, single-use code the owner types into the desktop companion."""
    __tablename__ = "device_pairing_codes"
    owner_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("owners.id", ondelete="CASCADE"), index=True)
    code_hash: Mapped[str] = mapped_column(String(64), unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class DeviceTask(IdMixin, TimestampMixin, Base):
    """A unit of browser work assigned to exactly one executor (cloud or one device)."""
    __tablename__ = "device_tasks"
    __table_args__ = (Index("ix_device_tasks_claim", "executor", "status"),)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    target_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("research_targets.id", ondelete="SET NULL"))
    kind: Mapped[str] = mapped_column(String(24))  # record
    executor: Mapped[str] = mapped_column(String(16))  # cloud|local
    device_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("devices.id", ondelete="SET NULL"))
    status: Mapped[str] = mapped_column(String(16), default="queued")  # queued|claimed|done|failed
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    result: Mapped[dict | None] = mapped_column(JSON)
    error: Mapped[str | None] = mapped_column(Text)
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
