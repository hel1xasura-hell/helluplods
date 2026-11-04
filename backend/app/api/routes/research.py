import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.deps import audit, get_current_owner
from app.core.config import get_settings
from app.db.session import get_db, get_sessionmaker
from app.models import Owner, Project, ResearchReport, ResearchTarget, Screenshot, StorageObject
from app.services.research import CaptureFn, run_research
from app.services.storage import Storage, get_storage

router = APIRouter(prefix="/api", tags=["research"])


def get_capture_fn() -> CaptureFn | None:
    return None  # real Playwright capture; tests override with a fake


def get_session_factory():
    return get_sessionmaker()


def _owned_target(target_id: uuid.UUID, owner: Owner, db: Session) -> ResearchTarget:
    target = db.scalar(
        select(ResearchTarget).join(Project, Project.id == ResearchTarget.project_id)
        .where(ResearchTarget.id == target_id, Project.owner_id == owner.id)
    )
    if target is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Target not found")
    return target


def _background(session_factory, target_id, storage: Storage, capture):
    with session_factory() as db:
        run_research(db, target_id, storage, capture)


@router.post("/targets/{target_id}/research", status_code=status.HTTP_202_ACCEPTED)
def start_research(
    target_id: uuid.UUID, request: Request, tasks: BackgroundTasks,
    owner: Owner = Depends(get_current_owner), db: Session = Depends(get_db),
    storage: Storage = Depends(get_storage), capture: CaptureFn | None = Depends(get_capture_fn),
    session_factory=Depends(get_session_factory),
):
    target = _owned_target(target_id, owner, db)
    if target.status in {"queued", "running"}:
        raise HTTPException(status.HTTP_409_CONFLICT, "Research is already in progress for this target")
    target.status = "queued"
    audit(db, owner.id, "research.started", request, target_id=str(target.id))
    db.commit()
    if get_settings().job_backend == "celery":
        from app.jobs.celery_app import research_target

        research_target.delay(str(target.id))
    else:
        tasks.add_task(_background, session_factory, target.id, storage, capture)
    return {"status": "queued"}


@router.get("/targets/{target_id}/report")
def get_report(target_id: uuid.UUID, owner: Owner = Depends(get_current_owner), db: Session = Depends(get_db)):
    target = _owned_target(target_id, owner, db)
    report = db.scalar(select(ResearchReport).where(ResearchReport.target_id == target.id)
                       .order_by(ResearchReport.created_at.desc()))
    if report is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No report yet")
    return {"id": str(report.id), "target_id": str(target.id), "tested_hands_on": report.tested_hands_on,
            "verified_at": report.verified_at, "body": report.body}


@router.get("/screenshots/{screenshot_id}")
def get_screenshot(
    screenshot_id: uuid.UUID, owner: Owner = Depends(get_current_owner), db: Session = Depends(get_db),
    storage: Storage = Depends(get_storage),
):
    row = db.execute(
        select(Screenshot, StorageObject).join(Project, Project.id == Screenshot.project_id)
        .join(StorageObject, StorageObject.id == Screenshot.storage_object_id)
        .where(Screenshot.id == screenshot_id, Project.owner_id == owner.id)
    ).first()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Screenshot not found")
    return Response(storage.get(row[1].key), media_type="image/png",
                    headers={"Content-Disposition": "inline", "X-Content-Type-Options": "nosniff"})


@router.get("/projects/{project_id}/screenshots")
def list_screenshots(project_id: uuid.UUID, owner: Owner = Depends(get_current_owner), db: Session = Depends(get_db)):
    from app.auth.deps import get_owned_project

    get_owned_project(project_id, owner, db)
    rows = db.scalars(select(Screenshot).where(Screenshot.project_id == project_id)
                      .order_by(Screenshot.created_at.desc()).limit(50)).all()
    return [{"id": str(s.id), "url": s.url, "captured_at": s.captured_at.isoformat() if s.captured_at else None} for s in rows]
