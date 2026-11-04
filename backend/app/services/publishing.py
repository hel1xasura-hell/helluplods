"""Approval workflow, upload queueing, resumable uploads with recovery, quota and duplicate protection."""
import asyncio
import time
import uuid
from collections.abc import Callable
from datetime import datetime, timezone

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.crypto import decrypt, encrypt
from app.integrations import youtube_logic as yl
from app.integrations.youtube_client import YouTubeClient, YouTubeError
from app.models import (
    Approval, Notification, Owner, Project, StorageObject, Thumbnail, UploadJob, VideoAsset, VideoRender, YouTubeAccount,
)
from app.services.script_meta import script_context
from app.services.storage import Storage

FINISHED = {"uploaded", "scheduled", "published"}
ACTIVE = {"queued", "uploading"}


class PublishError(Exception):
    def __init__(self, status: int, message: str, problems: list[dict] | None = None):
        super().__init__(message)
        self.status, self.problems = status, problems or []


# ---------- defaults, quota ----------
def owner_defaults(owner: Owner) -> dict:
    return dict((owner.settings or {}).get("publish_defaults", {}))


def reset_quota_if_new_day(acct: YouTubeAccount, now: datetime) -> None:
    today = yl.quota_day(now)
    if acct.quota_day != today:
        acct.quota_day, acct.quota_used_today = today, 0


def quota_summary(acct: YouTubeAccount, now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    limit = get_settings().youtube_daily_quota
    used = acct.quota_used_today if acct.quota_day == yl.quota_day(now) else 0
    cost = yl.upload_cost(True, get_settings().youtube_upload_cost)
    return {"quota_limit": limit, "quota_used_today": used, "uploads_left_today": max(0, (limit - used) // cost)}


def uploads_today(db: Session, owner_id: uuid.UUID, now: datetime) -> int:
    day = yl.quota_day(now)
    rows = db.scalars(select(UploadJob).join(Project, Project.id == UploadJob.project_id)
                      .where(Project.owner_id == owner_id, UploadJob.status.in_(list(FINISHED) + list(ACTIVE)))).all()
    return sum(1 for j in rows if yl.quota_day(j.created_at if j.created_at.tzinfo else j.created_at.replace(tzinfo=timezone.utc)) == day)


def existing_titles(db: Session, owner_id: uuid.UUID) -> set[str]:
    rows = db.scalars(select(UploadJob).join(Project, Project.id == UploadJob.project_id)
                      .where(Project.owner_id == owner_id, UploadJob.status.notin_(["failed", "cancelled"]))).all()
    return {((j.metadata_json or {}).get("resource", {}).get("snippet", {}).get("title") or "").lower() for j in rows} - {""}


def selected_thumbnail(db: Session, project_id: uuid.UUID) -> Thumbnail | None:
    return db.scalar(select(Thumbnail).where(Thumbnail.project_id == project_id, Thumbnail.selected.is_(True)))


# ---------- queueing ----------
def queue_upload(db: Session, owner: Owner, render: VideoRender, account: YouTubeAccount, *, visibility: str,
                 publish_at: datetime | None, made_for_kids: bool, synthetic: bool, upload_at: datetime | None = None,
                 approval: Approval | None = None, automatic: bool = False, now: datetime | None = None) -> UploadJob:
    now = now or datetime.now(timezone.utc)
    if account.owner_id != owner.id:
        raise PublishError(404, "YouTube account not found")
    if account.status != "connected":
        raise PublishError(409, "This YouTube connection needs to be reconnected")
    ctx = script_context(db, render)
    problems = yl.evaluate_policy(
        render={"status": render.status, "quality": render.quality or []}, metadata=ctx["metadata"],
        accuracy_warnings=ctx["accuracy_warnings"],
        defaults=owner_defaults(owner) if automatic else {}, uploads_today=uploads_today(db, owner.id, now),
        existing_titles=existing_titles(db, owner.id), uses_tts=ctx["uses_tts"], automatic=automatic)
    if ctx["uses_tts"] and not synthetic:
        problems.append({"code": "synthetic_disclosure", "message": "Narration is AI-generated, so synthetic-content disclosure must be on"})
    if problems:
        raise PublishError(422, "; ".join(p["message"] for p in problems), problems)
    try:
        resource = yl.build_video_resource(ctx["metadata"], visibility, publish_at, made_for_kids, synthetic,
                                           ctx["chapters_text"], ctx["language"])
    except ValueError as exc:
        raise PublishError(422, str(exc)) from exc
    thumb = selected_thumbnail(db, render.project_id)
    reset_quota_if_new_day(account, now)
    if not yl.can_afford(account.quota_used_today, yl.upload_cost(bool(thumb), get_settings().youtube_upload_cost), get_settings().youtube_daily_quota):
        raise PublishError(429, f"Today's YouTube quota is used up ({account.quota_used_today} units). "
                                "Try again after midnight Pacific time, or request a higher quota from Google.")
    meta = {"resource": resource, "made_for_kids": made_for_kids, "synthetic": synthetic,
            "thumbnail_id": str(thumb.id) if thumb else None}
    job = db.scalar(select(UploadJob).where(UploadJob.render_id == render.id, UploadJob.account_id == account.id))
    if job is not None:
        if job.status not in {"failed", "cancelled"}:
            raise PublishError(409, "This video was already queued or uploaded to that channel")
        job.status, job.error, job.progress = "queued", None, 0.0
        if job.youtube_video_id:  # never upload twice
            raise PublishError(409, "This video already exists on YouTube")
    else:
        job = UploadJob(project_id=render.project_id, render_id=render.id, account_id=account.id)
        db.add(job)
    job.visibility, job.publish_at, job.upload_at, job.metadata_json = visibility, publish_at, upload_at, meta
    job.approval_id = approval.id if approval else None
    db.flush()
    return job


# ---------- approvals ----------
def create_pending_approval(db: Session, render: VideoRender, note: str | None = None, status: str = "pending") -> Approval:
    ap = Approval(project_id=render.project_id, render_id=render.id, status=status, note=note)
    db.add(ap)
    db.flush()
    return ap


def after_render(db: Session, render: VideoRender) -> UploadJob | None:
    """Called when a render finishes. Approval mode: queue it for review. Automatic mode: publish only if every policy
    check passes, otherwise fall back to review with the reasons."""
    if render.status != "ready" or db.scalar(select(Approval).where(Approval.render_id == render.id)):
        return None
    project = db.get(Project, render.project_id)
    owner = db.get(Owner, project.owner_id)
    note = None
    if project.publishing_mode == "automatic":
        account = db.scalar(select(YouTubeAccount).where(YouTubeAccount.owner_id == owner.id, YouTubeAccount.status == "connected"))
        d = owner_defaults(owner)
        if account is None:
            note = "Needs your review: no YouTube channel is connected."
        else:
            now = datetime.now(timezone.utc)
            taken = [t for j in db.scalars(select(UploadJob).where(UploadJob.status.in_(list(FINISHED) + list(ACTIVE)))).all()
                     for t in [j.publish_at or j.upload_at] if t]
            slot = yl.next_publish_slot(d.get("publish_hours_utc", []), taken, now, int(d.get("daily_limit", 0) or 0)) if d.get("publish_hours_utc") else None
            ap = create_pending_approval(db, render, "Automatically approved by policy checks", "auto_approved")
            try:
                job = queue_upload(db, owner, render, account, visibility=d.get("visibility", "private"), publish_at=slot,
                                   made_for_kids=bool(d.get("made_for_kids")), synthetic=bool(d.get("contains_synthetic_media")),
                                   approval=ap, automatic=True, now=now)
                db.add(Notification(owner_id=owner.id, kind="publishing", title="Video queued for automatic upload", body=job.metadata_json["resource"]["snippet"]["title"][:200]))
                return job
            except PublishError as exc:
                ap.status, ap.note = "pending", "Needs your review: " + str(exc)
                db.add(Notification(owner_id=owner.id, kind="approval", title="Video needs your review", body=str(exc)[:300]))
                return None
    ap = create_pending_approval(db, render, note)
    db.add(Notification(owner_id=owner.id, kind="approval", title="Video awaiting approval", body=note or "Review the quality checks, then approve."))
    return None


# ---------- the upload itself ----------
def claim_job(db: Session, job_id: uuid.UUID) -> UploadJob | None:
    won = db.execute(update(UploadJob).where(UploadJob.id == job_id, UploadJob.status == "queued").values(status="uploading"))
    db.commit()
    return db.get(UploadJob, job_id) if won.rowcount == 1 else None


def run_upload(db: Session, job_id: uuid.UUID, storage: Storage, client: YouTubeClient,
               sleep: Callable[[float], None] | None = None, now: datetime | None = None) -> None:
    job = claim_job(db, job_id)
    if job is None:
        return
    job.attempts += 1
    account = db.get(YouTubeAccount, job.account_id)
    project = db.get(Project, job.project_id)
    title = job.metadata_json["resource"]["snippet"]["title"]

    def fail(message: str):
        job.status, job.error = "failed", message[:500]
        db.add(Notification(owner_id=project.owner_id, kind="publishing", title="Upload failed", body=f"{title}: {message}"[:300]))
        db.commit()

    try:
        if job.youtube_video_id:  # already on YouTube: never upload a duplicate
            return finalise(db, job, project, title)
        access = asyncio.run(client.refresh_access_token(decrypt(account.refresh_token_encrypted)))
    except YouTubeError as exc:
        if "invalid_grant" in str(exc):
            account.status = "reauthorize"
            return fail("YouTube access was revoked or expired. Reconnect your channel.")
        return fail(f"Couldn't sign in to YouTube: {exc}")
    except Exception as exc:
        return fail(f"{type(exc).__name__}: {exc}")

    render = db.get(VideoRender, job.render_id)
    data = storage.get(db.get(StorageObject, db.get(VideoAsset, render.video_asset_id).storage_object_id).key)
    total = len(data)
    now = now or datetime.now(timezone.utc)
    reset_quota_if_new_day(account, now)
    try:
        offset, video_id = 0, None
        if job.session_uri_encrypted:  # resume where a previous attempt stopped
            kind, val = asyncio.run(client.query_progress(decrypt(job.session_uri_encrypted), total))
            offset, video_id = (int(val), None) if kind == "incomplete" else (total, str(val))
            session = decrypt(job.session_uri_encrypted)
        else:
            cost = yl.upload_cost(False, get_settings().youtube_upload_cost)
            if not yl.can_afford(account.quota_used_today, cost, get_settings().youtube_daily_quota):
                return fail("Today's YouTube quota is used up. Retry after midnight Pacific time.")
            session = asyncio.run(client.start_upload(access, job.metadata_json["resource"], total))
            account.quota_used_today += cost  # reserved when the video insert starts
            job.session_uri_encrypted = encrypt(session)
            db.commit()
        for start, end in yl.plan_chunks(total):
            if video_id or end < offset:
                continue
            db.refresh(job)
            if job.status == "cancelled":
                return
            chunk, tries = data[max(start, offset):end + 1], 0
            while True:
                try:
                    kind, val = asyncio.run(client.upload_chunk(session, chunk, max(start, offset), total))
                    break
                except YouTubeError as exc:
                    tries += 1
                    if not exc.retriable or tries >= 4:
                        raise
                    (sleep or time.sleep)(min(2 ** tries, 30))
            job.bytes_uploaded = end + 1 if kind == "incomplete" else total
            job.progress = round(job.bytes_uploaded / total, 3)
            db.commit()
            if kind == "complete":
                video_id = str(val)
                break
        if not video_id:
            return fail("Upload ended without a video id. Retry to resume.")
        job.youtube_video_id = video_id
        db.commit()
    except YouTubeError as exc:
        if exc.reason == "uploadLimitExceeded":
            return fail("Your YouTube channel's own 24-hour upload limit was reached (this is separate from API quota). "
                        "Wait and retry; manual uploads count toward it too.")
        return fail(f"YouTube rejected the upload: {exc} (retry will resume)")
    except Exception as exc:
        return fail(f"{type(exc).__name__}: {exc} (retry will resume)")

    thumb_id = job.metadata_json.get("thumbnail_id")
    if thumb_id:
        try:
            th = db.get(Thumbnail, uuid.UUID(thumb_id))
            png = storage.get(db.get(StorageObject, th.storage_object_id).key)
            asyncio.run(client.set_thumbnail(access, job.youtube_video_id, png))
            account.quota_used_today += yl.QUOTA_COST["thumbnails.set"]
        except Exception as exc:  # the video is up; a thumbnail problem must not fail the upload
            job.metadata_json = {**job.metadata_json, "warnings": [f"Thumbnail was not set: {exc}"]}
    finalise(db, job, project, title)


def finalise(db: Session, job: UploadJob, project: Project, title: str) -> None:
    job.status = "scheduled" if job.publish_at else ("uploaded" if job.visibility == "private" else "published")
    job.progress, job.error = 1.0, None
    db.add(Notification(owner_id=project.owner_id, kind="publishing", title={"scheduled": "Video scheduled", "uploaded": "Video uploaded (private)", "published": "Video published"}[job.status], body=title[:200]))
    db.commit()


def due_jobs(db: Session, now: datetime | None = None) -> list[uuid.UUID]:
    """Queued jobs whose scheduled upload time has come, plus orphans whose immediate trigger was lost."""
    now = now or datetime.now(timezone.utc)
    rows = db.scalars(select(UploadJob).where(UploadJob.status == "queued")).all()
    out = []
    for j in rows:
        at = j.upload_at
        if at is not None and at.tzinfo is None:
            at = at.replace(tzinfo=timezone.utc)
        created = j.created_at if j.created_at.tzinfo else j.created_at.replace(tzinfo=timezone.utc)
        if (at is not None and at <= now) or (at is None and (now - created).total_seconds() > 120):
            out.append(j.id)
    return out
