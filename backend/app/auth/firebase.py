import json
import os
from functools import lru_cache

import firebase_admin
from firebase_admin import auth as fb_auth
from firebase_admin import credentials

from app.core.config import get_settings


class AuthNotConfigured(RuntimeError):
    pass


@lru_cache
def _app() -> firebase_admin.App:
    s = get_settings()
    if not s.firebase_project_id:
        raise AuthNotConfigured("FIREBASE_PROJECT_ID is not set.")
    cred = None
    raw = s.firebase_credentials.strip()
    if raw:
        cred = credentials.Certificate(json.loads(raw) if raw.startswith("{") else os.path.expanduser(raw))
    return firebase_admin.initialize_app(cred, {"projectId": s.firebase_project_id})


def verify_id_token(token: str) -> dict:
    """Verify a Firebase ID token. Revocation is checked only when service-account credentials exist."""
    has_creds = bool(get_settings().firebase_credentials.strip())
    return fb_auth.verify_id_token(token, app=_app(), check_revoked=has_creds)
