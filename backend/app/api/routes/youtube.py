import asyncio
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.deps import audit, get_current_owner
from app.core.config import get_settings
from app.core.crypto import CryptoNotConfigured, decrypt, encrypt
from app.db.session import get_db
from app.integrations import youtube_logic as yl
from app.integrations.youtube_client import YouTubeClient, YouTubeError
from app.models import Owner, YouTubeAccount
from app.services.publishing import quota_summary

router = APIRouter(prefix="/api/youtube", tags=["youtube"])


def get_youtube_client() -> YouTubeClient:
    s = get_settings()
    return YouTubeClient(s.youtube_client_id, s.youtube_client_secret, s.youtube_redirect_uri)


def _missing() -> list[str]:
    s = get_settings()
    return [n for n, v in (("YOUTUBE_CLIENT_ID", s.youtube_client_id), ("YOUTUBE_CLIENT_SECRET", s.youtube_client_secret),
                           ("YOUTUBE_REDIRECT_URI", s.youtube_redirect_uri), ("TOKEN_ENCRYPTION_KEY", s.token_encryption_key)) if not v]


@router.get("/status")
def youtube_status(owner: Owner = Depends(get_current_owner), db: Session = Depends(get_db)):
    s = get_settings()
    accounts = db.scalars(select(YouTubeAccount).where(YouTubeAccount.owner_id == owner.id)).all()
    return {
        "configured": not _missing(), "missing": _missing(),
        "accounts": [{"id": str(a.id), "channel_id": a.channel_id, "channel_title": a.channel_title, "status": a.status,
                      **quota_summary(a)} for a in accounts],
        "daily_quota": s.youtube_daily_quota,
        "uploads_per_day_at_this_quota": yl.uploads_per_day(s.youtube_daily_quota, True, s.youtube_upload_cost),
        "upload_cost_units": s.youtube_upload_cost,
        "quota_note": f"Each upload costs about {s.youtube_upload_cost + 50:,} quota units (set YOUTUBE_UPLOAD_COST if your Cloud "
                      "Console shows a different cost). More than that per day needs a quota extension approved by Google.",
        "audit_note": "Google forces videos uploaded by an API project that has not passed its compliance audit to stay PRIVATE, "
                      "whatever visibility you choose. Request the audit before relying on public or unlisted uploads.",
        "scopes": yl.SCOPES,
    }


@router.post("/oauth/start")
def oauth_start(request: Request, owner: Owner = Depends(get_current_owner), db: Session = Depends(get_db),
                client: YouTubeClient = Depends(get_youtube_client)):
    if _missing():
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, f"YouTube isn't configured yet. Missing: {', '.join(_missing())}")
    verifier, challenge = yl.new_pkce()
    state = yl.make_state(get_settings().token_encryption_key, str(owner.id), verifier)
    audit(db, owner.id, "youtube.oauth_started", request)
    db.commit()
    return {"auth_url": client.auth_url(state, challenge)}


@router.get("/oauth/callback")
def oauth_callback(request: Request, state: str = "", code: str = "", error: str = "", db: Session = Depends(get_db),
                   client: YouTubeClient = Depends(get_youtube_client)):
    """Google redirects the browser here. Identity comes from the encrypted state, not from a header."""
    base = get_settings().frontend_base + "/publishing"
    if error or not code or not state:
        return RedirectResponse(f"{base}?error=cancelled")
    try:
        st = yl.read_state(get_settings().token_encryption_key, state)
        owner = db.get(Owner, uuid.UUID(st["owner_id"]))
        if owner is None:
            raise yl.OAuthStateError("unknown owner")
        tokens = asyncio.run(client.exchange_code(code, st["verifier"]))
        if not tokens.refresh_token:
            return RedirectResponse(f"{base}?error=no_refresh_token")
        info = asyncio.run(client.channel_info(tokens.access_token))
    except (yl.OAuthStateError, ValueError):
        return RedirectResponse(f"{base}?error=invalid_state")
    except YouTubeError as exc:
        return RedirectResponse(f"{base}?error=google_{exc.status or 'error'}")
    except CryptoNotConfigured:
        return RedirectResponse(f"{base}?error=not_configured")
    acct = db.scalar(select(YouTubeAccount).where(YouTubeAccount.owner_id == owner.id, YouTubeAccount.channel_id == info["id"]))
    if acct is None:
        acct = YouTubeAccount(owner_id=owner.id, channel_id=info["id"], channel_title=info["title"],
                              refresh_token_encrypted=encrypt(tokens.refresh_token))
        db.add(acct)
    else:
        acct.refresh_token_encrypted, acct.channel_title, acct.status = encrypt(tokens.refresh_token), info["title"], "connected"
    audit(db, owner.id, "youtube.connected", request, channel_id=info["id"])
    db.commit()
    return RedirectResponse(f"{base}?connected=1")


@router.delete("/accounts/{account_id}", status_code=status.HTTP_204_NO_CONTENT)
def disconnect(account_id: uuid.UUID, request: Request, owner: Owner = Depends(get_current_owner),
               db: Session = Depends(get_db), client: YouTubeClient = Depends(get_youtube_client)):
    """Removes our stored token. Never touches the channel or its videos."""
    acct = db.scalar(select(YouTubeAccount).where(YouTubeAccount.id == account_id, YouTubeAccount.owner_id == owner.id))
    if acct is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Account not found")
    try:
        asyncio.run(client.revoke(decrypt(acct.refresh_token_encrypted)))
    except Exception:
        pass  # revoking at Google is best-effort; we still delete our copy
    audit(db, owner.id, "youtube.disconnected", request, channel_id=acct.channel_id)
    acct.refresh_token_encrypted, acct.status = "", "disconnected"
    db.commit()
