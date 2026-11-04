import asyncio
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.routes.youtube import get_youtube_client
from app.auth.deps import audit, get_current_owner
from app.core.crypto import decrypt
from app.db.session import get_db
from app.integrations.youtube_client import YouTubeClient, YouTubeError
from app.models import (
    AgentRun, AnalyticsSnapshot, Approval, Owner, Project, Recording, UploadJob, VideoRender, YouTubeAccount,
)
from app.services import ops
from app.services.publishing import reset_quota_if_new_day

router = APIRouter(prefix="/api/analytics", tags=["analytics"])


def _aware(t: datetime) -> datetime:
    return t if t.tzinfo else t.replace(tzinfo=timezone.utc)


@router.get("/production")
def production(days: int = 14, owner: Owner = Depends(get_current_owner), db: Session = Depends(get_db)):
    """Throughput and reliability computed from your own records."""
    days = max(1, min(days, 90))
    since = datetime.now(timezone.utc) - timedelta(days=days)
    mine = select(Project.id).where(Project.owner_id == owner.id)
    renders = [r for r in db.scalars(select(VideoRender).where(VideoRender.project_id.in_(mine))).all() if _aware(r.created_at) >= since]
    uploads = [u for u in db.scalars(select(UploadJob).where(UploadJob.project_id.in_(mine))).all() if _aware(u.created_at) >= since]
    approvals = db.scalars(select(Approval).where(Approval.project_id.in_(mine))).all()
    runs = [x for x in db.scalars(select(AgentRun).where(AgentRun.project_id.in_(mine))).all() if _aware(x.created_at) >= since]
    recs = [x for x in db.scalars(select(Recording).where(Recording.project_id.in_(mine))).all() if _aware(x.created_at) >= since]

    finished = [r for r in renders if r.status in {"ready", "failed"}]
    ready = [r for r in renders if r.status == "ready"]
    failing: dict[str, int] = {}
    for r in renders:
        for c in r.quality or []:
            if c.get("status") in {"fail", "warn"}:
                failing[c["name"]] = failing.get(c["name"], 0) + 1
    done_up = [u for u in uploads if u.status in {"uploaded", "scheduled", "published"}]
    return {
        "days": days,
        "renders_per_day": ops.daily_counts([r.created_at for r in renders], min(days, 30)),
        "uploads_per_day": ops.daily_counts([u.created_at for u in done_up], min(days, 30)),
        "totals": {"renders": len(renders), "renders_ready": len(ready), "uploads": len(done_up),
                   "recordings": len(recs), "research_runs": len(runs)},
        "render_success_rate": ops.rate(len(ready), len(finished)),
        "upload_success_rate": ops.rate(len(done_up), len([u for u in uploads if u.status in {"uploaded", "scheduled", "published", "failed"}])),
        "avg_render_seconds": ops.average([(_aware(r.updated_at) - _aware(r.created_at)).total_seconds() for r in ready]),
        "approval_funnel": {s: sum(1 for a in approvals if a.status == s) for s in ("pending", "approved", "auto_approved", "rejected")},
        "most_flagged_quality_checks": sorted(failing.items(), key=lambda kv: kv[1], reverse=True)[:5],
        "target_per_day": 50,
        "progress_toward_target": ops.rate(len(done_up), 50 * days),
    }


@router.get("/youtube")
def youtube_stats(owner: Owner = Depends(get_current_owner), db: Session = Depends(get_db)):
    """Latest stored statistics for each uploaded video (refresh with POST /sync)."""
    jobs = db.scalars(select(UploadJob).join(Project, Project.id == UploadJob.project_id)
                      .where(Project.owner_id == owner.id, UploadJob.youtube_video_id.is_not(None))
                      .order_by(UploadJob.created_at.desc()).limit(50)).all()
    out = []
    for j in jobs:
        snap = db.scalar(select(AnalyticsSnapshot).where(AnalyticsSnapshot.youtube_video_id == j.youtube_video_id)
                         .order_by(AnalyticsSnapshot.created_at.desc()))
        out.append({"video_id": j.youtube_video_id, "title": (j.metadata_json or {}).get("resource", {}).get("snippet", {}).get("title"),
                    "status": j.status, "views": (snap.metrics or {}).get("viewCount") if snap else None,
                    "likes": (snap.metrics or {}).get("likeCount") if snap else None,
                    "comments": (snap.metrics or {}).get("commentCount") if snap else None,
                    "fetched_at": snap.created_at.isoformat() if snap else None})
    return {"videos": out, "totals": {k: sum(v[k] or 0 for v in out) for k in ("views", "likes", "comments")}}


@router.post("/youtube/sync")
def sync_youtube(request: Request, owner: Owner = Depends(get_current_owner), db: Session = Depends(get_db),
                 client: YouTubeClient = Depends(get_youtube_client)):
    acct = db.scalar(select(YouTubeAccount).where(YouTubeAccount.owner_id == owner.id, YouTubeAccount.status == "connected"))
    if acct is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Connect a YouTube channel first")
    jobs = db.scalars(select(UploadJob).join(Project, Project.id == UploadJob.project_id)
                      .where(Project.owner_id == owner.id, UploadJob.youtube_video_id.is_not(None))).all()
    ids = sorted({j.youtube_video_id for j in jobs})
    if not ids:
        return {"synced": 0}
    try:
        access = asyncio.run(client.refresh_access_token(decrypt(acct.refresh_token_encrypted)))
        stats: dict[str, dict] = {}
        for i in range(0, len(ids), 50):
            stats.update(asyncio.run(client.video_stats(access, ids[i:i + 50])))
            reset_quota_if_new_day(acct, datetime.now(timezone.utc))
            acct.quota_used_today += 1
    except YouTubeError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"YouTube said: {exc}") from exc
    for vid, metrics in stats.items():
        db.add(AnalyticsSnapshot(youtube_video_id=vid, metrics=metrics))
    audit(db, owner.id, "analytics.synced", request, videos=len(stats))
    db.commit()
    return {"synced": len(stats)}
