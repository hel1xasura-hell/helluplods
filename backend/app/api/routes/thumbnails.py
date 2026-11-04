import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.auth.deps import audit, get_current_owner, get_owned_project
from app.db.session import get_db
from app.media.thumbnail import TEMPLATES, render_thumbnail
from app.models import Owner, Project, Screenshot, StorageObject, Thumbnail
from app.services.storage import Storage, get_storage

router = APIRouter(prefix="/api", tags=["thumbnails"])


class ThumbIn(BaseModel):
    text: str = Field(min_length=1, max_length=80)
    template: str = Field(default="bold_left")
    accent: str = Field(default="#8d6bff", pattern=r"^#[0-9a-fA-F]{6}$")
    screenshot_id: uuid.UUID | None = None
    brand: str | None = Field(default=None, max_length=24)


def serialize(t: Thumbnail) -> dict:
    return {"id": str(t.id), "text": t.text, "template": t.template, "accent": t.accent, "selected": t.selected,
            "created_at": t.created_at.isoformat()}


@router.get("/thumbnail-templates")
def templates(_: Owner = Depends(get_current_owner)):
    return list(TEMPLATES)


@router.post("/projects/{project_id}/thumbnails", status_code=status.HTTP_201_CREATED)
def create_thumbnail(project_id: uuid.UUID, body: ThumbIn, request: Request, owner: Owner = Depends(get_current_owner),
                     db: Session = Depends(get_db), storage: Storage = Depends(get_storage)):
    project = get_owned_project(project_id, owner, db)
    if body.template not in TEMPLATES:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"Template must be one of {', '.join(TEMPLATES)}")
    shot_bytes = None
    if body.screenshot_id:
        row = db.execute(select(Screenshot, StorageObject).join(StorageObject, StorageObject.id == Screenshot.storage_object_id)
                         .where(Screenshot.id == body.screenshot_id, Screenshot.project_id == project.id)).first()
        if row is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Screenshot not found in this project")
        shot_bytes = storage.get(row[1].key)
    try:
        png = render_thumbnail(body.text, body.template, body.accent, screenshot=shot_bytes, brand=body.brand)
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
    key = f"{project.owner_id}/{project.id}/thumbnails/{uuid.uuid4()}.png"
    meta = storage.put(key, png, "image/png")
    obj = StorageObject(owner_id=project.owner_id, backend=storage.backend, key=key, content_type="image/png",
                        size_bytes=meta["size_bytes"], sha256=meta["sha256"])
    db.add(obj)
    db.flush()
    t = Thumbnail(project_id=project.id, storage_object_id=obj.id, text=body.text, template=body.template, accent=body.accent)
    db.add(t)
    audit(db, owner.id, "thumbnail.created", request, project_id=str(project.id))
    db.commit()
    return serialize(t)


def _thumb(thumb_id: uuid.UUID, owner: Owner, db: Session) -> Thumbnail:
    row = db.scalar(select(Thumbnail).join(Project, Project.id == Thumbnail.project_id)
                    .where(Thumbnail.id == thumb_id, Project.owner_id == owner.id))
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Thumbnail not found")
    return row


@router.get("/projects/{project_id}/thumbnails")
def list_thumbnails(project_id: uuid.UUID, owner: Owner = Depends(get_current_owner), db: Session = Depends(get_db)):
    get_owned_project(project_id, owner, db)
    rows = db.scalars(select(Thumbnail).where(Thumbnail.project_id == project_id).order_by(Thumbnail.created_at.desc())).all()
    return [serialize(t) for t in rows]


@router.get("/thumbnails/{thumb_id}/file")
def thumbnail_file(thumb_id: uuid.UUID, download: bool = False, owner: Owner = Depends(get_current_owner),
                   db: Session = Depends(get_db), storage: Storage = Depends(get_storage)):
    t = _thumb(thumb_id, owner, db)
    data = storage.get(db.get(StorageObject, t.storage_object_id).key)
    disp = 'attachment; filename="thumbnail.png"' if download else "inline"
    return Response(data, media_type="image/png", headers={"Content-Disposition": disp, "X-Content-Type-Options": "nosniff"})


@router.post("/thumbnails/{thumb_id}/select")
def select_thumbnail(thumb_id: uuid.UUID, owner: Owner = Depends(get_current_owner), db: Session = Depends(get_db)):
    t = _thumb(thumb_id, owner, db)
    db.execute(update(Thumbnail).where(Thumbnail.project_id == t.project_id).values(selected=False))
    t.selected = True
    db.commit()
    return serialize(t)


@router.delete("/thumbnails/{thumb_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_thumbnail(thumb_id: uuid.UUID, owner: Owner = Depends(get_current_owner), db: Session = Depends(get_db)):
    db.delete(_thumb(thumb_id, owner, db))
    db.commit()
