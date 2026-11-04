import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class OwnerOut(ORM):
    id: uuid.UUID
    email: str
    display_name: str | None = None


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=5000)
    execution_mode: Literal["cloud", "local", "both"] = "cloud"
    publishing_mode: Literal["approval", "automatic"] = "approval"


class ProjectOut(ORM):
    id: uuid.UUID
    name: str
    description: str | None
    status: str
    execution_mode: str
    publishing_mode: str
    created_at: datetime


class TargetCreate(BaseModel):
    kind: Literal["website_url", "website_name", "android_app", "play_url"]
    value: str = Field(min_length=1, max_length=2048)

    @field_validator("value")
    @classmethod
    def strip(cls, v: str) -> str:
        return v.strip()


class TargetOut(ORM):
    id: uuid.UUID
    project_id: uuid.UUID
    kind: str
    value: str
    canonical_url: str | None
    status: str
    error: str | None = None
    created_at: datetime


class AgentOut(BaseModel):
    key: str
    name: str
    responsibilities: str
    stage: int
    implemented: bool
    allowed_tools: list[str]
    timeout_seconds: float
    max_retries: int


class DashboardOut(BaseModel):
    total_projects: int
    research_tasks: int
    active_agents: int
    videos_rendering: int
    videos_awaiting_approval: int
    published_videos: int
    failed_jobs: int
    processing_queue: int
    storage_bytes: int
    cloud_workers: Literal["not_connected", "online"]
    local_workers: int
    recent_activity: list[dict]
