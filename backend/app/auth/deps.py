import logging
import uuid

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import firebase
from app.core.config import get_settings
from app.db.session import get_db
from app.models import AuditEvent, Owner, Project

log = logging.getLogger(__name__)
bearer = HTTPBearer(auto_error=False)


def verify_token(token: str) -> dict:
    """Indirection so tests can override verification without touching Firebase."""
    return firebase.verify_id_token(token)


def audit(db: Session, owner_id, action: str, request: Request | None = None, **detail) -> None:
    ip = request.client.host if request and request.client else None
    db.add(AuditEvent(owner_id=owner_id, action=action, ip=ip, detail=detail))


def owner_from_token(token: str, db: Session, request: Request | None = None) -> Owner:
    """Verify a Firebase token and return the single owner. Raises HTTPException on any failure."""
    try:
        claims = verify_token(token)
    except firebase.AuthNotConfigured as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc)) from exc
    except Exception as exc:  # invalid, expired, revoked
        log.info("token verification failed", extra={"ctx": {"error": type(exc).__name__}})
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid token") from exc

    owner_email = get_settings().owner_email.strip().lower()
    email = (claims.get("email") or "").lower()
    if not owner_email:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "OWNER_EMAIL is not configured")
    if not claims.get("email_verified") or email != owner_email:
        audit(db, None, "auth.rejected_non_owner", request, email=email)
        db.commit()
        raise HTTPException(status.HTTP_403_FORBIDDEN, "This workspace is private")

    uid = claims["uid"] if "uid" in claims else claims.get("sub")
    owner = db.scalar(select(Owner).where(Owner.email == owner_email))
    if owner is None:
        owner = Owner(firebase_uid=uid, email=owner_email, display_name=claims.get("name"))
        db.add(owner)
        audit(db, None, "owner.initialized", request, email=owner_email)
        db.commit()
    elif owner.firebase_uid != uid:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Owner identity mismatch")
    return owner


def get_current_owner(
    request: Request,
    creds: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: Session = Depends(get_db),
) -> Owner:
    if creds is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing bearer token")
    return owner_from_token(creds.credentials, db, request)


def get_owned_project(project_id: uuid.UUID, owner: Owner, db: Session) -> Project:
    """Every sensitive project query goes through here."""
    project = db.scalar(select(Project).where(Project.id == project_id, Project.owner_id == owner.id))
    if project is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Project not found")
    return project
