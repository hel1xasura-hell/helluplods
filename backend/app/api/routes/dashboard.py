from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth.deps import get_current_owner
from app.db.session import get_db
from app.models import (
    AgentRun, AuditEvent, Approval, Device, Owner, Project, ResearchTarget, StorageObject, UploadJob,
    VideoRender,
)
from app.schemas.api import DashboardOut
from app.services.heartbeat import online_workers

router = APIRouter(prefix="/api", tags=["dashboard"])


def _count(db: Session, stmt) -> int:
    return db.scalar(stmt) or 0


@router.get("/dashboard", response_model=DashboardOut)
def dashboard(owner: Owner = Depends(get_current_owner), db: Session = Depends(get_db)):
    mine = select(Project.id).where(Project.owner_id == owner.id)
    activity = db.scalars(
        select(AuditEvent).where(AuditEvent.owner_id == owner.id)
        .order_by(AuditEvent.created_at.desc()).limit(10)
    ).all()
    return DashboardOut(
        total_projects=_count(db, select(func.count()).select_from(Project).where(Project.owner_id == owner.id)),
        research_tasks=_count(db, select(func.count()).select_from(ResearchTarget)
                              .where(ResearchTarget.project_id.in_(mine))),
        active_agents=_count(db, select(func.count()).select_from(AgentRun)
                             .where(AgentRun.project_id.in_(mine), AgentRun.status == "running")),
        videos_rendering=_count(db, select(func.count()).select_from(VideoRender)
                                .where(VideoRender.project_id.in_(mine), VideoRender.status == "rendering")),
        videos_awaiting_approval=_count(db, select(func.count()).select_from(Approval)
                                        .where(Approval.project_id.in_(mine), Approval.status == "pending")),
        published_videos=_count(db, select(func.count()).select_from(UploadJob)
                                .where(UploadJob.project_id.in_(mine), UploadJob.status == "published")),
        failed_jobs=_count(db, select(func.count()).select_from(AgentRun)
                           .where(AgentRun.project_id.in_(mine), AgentRun.status == "failed")),
        processing_queue=_count(db, select(func.count()).select_from(AgentRun)
                                .where(AgentRun.project_id.in_(mine), AgentRun.status == "queued")),
        storage_bytes=_count(db, select(func.coalesce(func.sum(StorageObject.size_bytes), 0))
                             .where(StorageObject.owner_id == owner.id)),
        cloud_workers="online" if online_workers() else "not_connected",
        local_workers=_count(db, select(func.count()).select_from(Device)
                             .where(Device.owner_id == owner.id, Device.revoked_at.is_(None))),
        recent_activity=[
            {"action": a.action, "at": a.created_at.isoformat(), "detail": a.detail} for a in activity
        ],
    )
