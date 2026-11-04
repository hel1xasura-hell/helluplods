import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.deps import audit, get_current_owner, get_owned_project
from app.db.session import get_db
from app.models import Owner, Project, ResearchTarget
from app.schemas.api import ProjectCreate, ProjectOut, TargetCreate, TargetOut
from app.services.ssrf import UnsafeURL, validate_public_url

router = APIRouter(prefix="/api/projects", tags=["projects"])


@router.get("", response_model=list[ProjectOut])
def list_projects(owner: Owner = Depends(get_current_owner), db: Session = Depends(get_db)):
    return db.scalars(
        select(Project).where(Project.owner_id == owner.id).order_by(Project.created_at.desc())
    ).all()


@router.post("", response_model=ProjectOut, status_code=status.HTTP_201_CREATED)
def create_project(
    body: ProjectCreate, request: Request,
    owner: Owner = Depends(get_current_owner), db: Session = Depends(get_db),
):
    project = Project(owner_id=owner.id, **body.model_dump())
    db.add(project)
    db.flush()
    audit(db, owner.id, "project.created", request, project_id=str(project.id))
    db.commit()
    return project


@router.get("/{project_id}", response_model=ProjectOut)
def get_project(project_id: uuid.UUID, owner: Owner = Depends(get_current_owner), db: Session = Depends(get_db)):
    return get_owned_project(project_id, owner, db)


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_project(
    project_id: uuid.UUID, request: Request,
    owner: Owner = Depends(get_current_owner), db: Session = Depends(get_db),
):
    project = get_owned_project(project_id, owner, db)
    audit(db, owner.id, "project.deleted", request, project_id=str(project.id))
    db.delete(project)
    db.commit()


@router.get("/{project_id}/targets", response_model=list[TargetOut])
def list_targets(project_id: uuid.UUID, owner: Owner = Depends(get_current_owner), db: Session = Depends(get_db)):
    get_owned_project(project_id, owner, db)
    return db.scalars(select(ResearchTarget).where(ResearchTarget.project_id == project_id)
                      .order_by(ResearchTarget.created_at.desc())).all()


@router.post("/{project_id}/targets", response_model=TargetOut, status_code=status.HTTP_201_CREATED)
def add_target(
    project_id: uuid.UUID, body: TargetCreate, request: Request,
    owner: Owner = Depends(get_current_owner), db: Session = Depends(get_db),
):
    get_owned_project(project_id, owner, db)
    if body.kind in {"website_url", "play_url"}:
        try:
            validate_public_url(body.value)
        except UnsafeURL as exc:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"URL rejected: {exc}") from exc
    target = ResearchTarget(project_id=project_id, kind=body.kind, value=body.value)
    db.add(target)
    db.flush()
    audit(db, owner.id, "research_target.created", request, target_id=str(target.id), kind=body.kind)
    db.commit()
    return target
