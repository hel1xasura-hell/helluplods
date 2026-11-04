import uuid
from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, IdMixin, TimestampMixin


class Owner(IdMixin, TimestampMixin, Base):
    __tablename__ = "owners"
    firebase_uid: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    email: Mapped[str] = mapped_column(String(320), unique=True)
    display_name: Mapped[str | None] = mapped_column(String(200))
    settings: Mapped[dict] = mapped_column(JSON, default=dict)
    projects: Mapped[list["Project"]] = relationship(back_populates="owner")


class Project(IdMixin, TimestampMixin, Base):
    __tablename__ = "projects"
    __table_args__ = (Index("ix_projects_owner_status", "owner_id", "status"),)
    owner_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("owners.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(32), default="draft")
    execution_mode: Mapped[str] = mapped_column(String(16), default="cloud")  # cloud|local|both
    publishing_mode: Mapped[str] = mapped_column(String(16), default="approval")  # approval|automatic
    owner: Mapped[Owner] = relationship(back_populates="projects")
    targets: Mapped[list["ResearchTarget"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )


class ResearchTarget(IdMixin, TimestampMixin, Base):
    __tablename__ = "research_targets"
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    kind: Mapped[str] = mapped_column(String(16))  # website_url|website_name|android_app|play_url
    value: Mapped[str] = mapped_column(String(2048))
    canonical_url: Mapped[str | None] = mapped_column(String(2048))
    status: Mapped[str] = mapped_column(String(24), default="pending")
    error: Mapped[str | None] = mapped_column(Text)
    project: Mapped[Project] = relationship(back_populates="targets")


class ResearchReport(IdMixin, TimestampMixin, Base):
    __tablename__ = "research_reports"
    target_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("research_targets.id", ondelete="CASCADE"), index=True
    )
    body: Mapped[dict] = mapped_column(JSON, default=dict)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    tested_hands_on: Mapped[bool] = mapped_column(default=False)


class Source(IdMixin, TimestampMixin, Base):
    __tablename__ = "sources"
    report_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("research_reports.id", ondelete="CASCADE"), index=True
    )
    url: Mapped[str] = mapped_column(String(2048))
    title: Mapped[str | None] = mapped_column(String(500))
    is_official: Mapped[bool] = mapped_column(default=False)
    fetched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (UniqueConstraint("report_id", "url", name="uq_source_report_url"),)
