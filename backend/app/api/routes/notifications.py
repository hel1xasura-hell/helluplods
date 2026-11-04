import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.auth.deps import get_current_owner
from app.db.session import get_db
from app.models import Notification, Owner

router = APIRouter(prefix="/api/notifications", tags=["notifications"])


@router.get("")
def list_notifications(owner: Owner = Depends(get_current_owner), db: Session = Depends(get_db)):
    rows = db.scalars(select(Notification).where(Notification.owner_id == owner.id)
                      .order_by(Notification.created_at.desc()).limit(20)).all()
    unread = db.scalar(select(func.count()).select_from(Notification)
                       .where(Notification.owner_id == owner.id, Notification.read_at.is_(None))) or 0
    return {"unread": unread, "items": [
        {"id": str(n.id), "kind": n.kind, "title": n.title, "body": n.body,
         "read": n.read_at is not None, "created_at": n.created_at.isoformat()} for n in rows]}


@router.post("/{notification_id}/read", status_code=status.HTTP_204_NO_CONTENT)
def mark_read(notification_id: uuid.UUID, owner: Owner = Depends(get_current_owner), db: Session = Depends(get_db)):
    n = db.scalar(select(Notification).where(Notification.id == notification_id, Notification.owner_id == owner.id))
    if n is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Notification not found")
    n.read_at = n.read_at or datetime.now(timezone.utc)
    db.commit()


@router.post("/read-all", status_code=status.HTTP_204_NO_CONTENT)
def mark_all_read(owner: Owner = Depends(get_current_owner), db: Session = Depends(get_db)):
    db.execute(update(Notification).where(Notification.owner_id == owner.id, Notification.read_at.is_(None))
               .values(read_at=datetime.now(timezone.utc)))
    db.commit()
