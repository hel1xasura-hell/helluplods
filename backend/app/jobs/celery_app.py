from celery import Celery
from celery.schedules import crontab

from app.core.config import get_settings

settings = get_settings()
celery_app = Celery("hell_uploads", broker=settings.redis_url, backend=settings.redis_url)
celery_app.conf.update(
    task_serializer="json", result_serializer="json", accept_content=["json"],
    task_acks_late=True, worker_prefetch_multiplier=1, task_track_started=True,
    task_routes={
        "browser.*": {"queue": "browser"},
        "render.*": {"queue": "render"},
        "default.*": {"queue": "default"},
    },
)


@celery_app.task(name="default.ping")
def ping() -> str:
    return "pong"


@celery_app.task(name="browser.research_target")
def research_target(target_id: str) -> None:
    import uuid

    from app.db.session import get_sessionmaker
    from app.services.research import run_research
    from app.services.storage import get_storage

    with get_sessionmaker()() as db:
        run_research(db, uuid.UUID(target_id), get_storage())


@celery_app.task(name="render.render_video")
def render_video(render_id: str) -> None:
    import uuid

    from app.db.session import get_sessionmaker
    from app.services.render_service import run_render
    from app.services.storage import get_storage

    with get_sessionmaker()() as db:
        upload_id = run_render(db, uuid.UUID(render_id), get_storage())
    if upload_id:
        upload_video.delay(str(upload_id))


@celery_app.task(name="default.upload_video")
def upload_video(job_id: str) -> None:
    import uuid

    from app.core.config import get_settings
    from app.db.session import get_sessionmaker
    from app.integrations.youtube_client import YouTubeClient
    from app.services.publishing import run_upload
    from app.services.storage import get_storage

    s = get_settings()
    client = YouTubeClient(s.youtube_client_id, s.youtube_client_secret, s.youtube_redirect_uri)
    with get_sessionmaker()() as db:
        run_upload(db, uuid.UUID(job_id), get_storage(), client)


@celery_app.task(name="default.publishing_tick")
def publishing_tick() -> int:
    from app.db.session import get_sessionmaker
    from app.services.publishing import due_jobs

    with get_sessionmaker()() as db:
        ids = due_jobs(db)
    for i in ids:
        upload_video.delay(str(i))
    return len(ids)


@celery_app.task(name="default.recover_stale")
def recover_stale_task() -> dict:
    from app.db.session import get_sessionmaker
    from app.services.maintenance import recover_stale

    with get_sessionmaker()() as db:
        return recover_stale(db)


@celery_app.task(name="default.backup")
def backup_task() -> str | None:
    from sqlalchemy import select

    from app.core.config import get_settings
    from app.db.session import get_sessionmaker
    from app.models import Owner
    from app.services.maintenance import run_backup
    from app.services.storage import get_storage

    with get_sessionmaker()() as db:
        owner = db.scalar(select(Owner))
        if owner is None:
            return None
        return str(run_backup(db, owner.id, get_storage(), get_settings().database_url).id)


@celery_app.task(name="default.heartbeat")
def heartbeat(worker_name: str = "worker") -> None:
    from app.services.heartbeat import beat

    beat(worker_name)


celery_app.conf.beat_schedule = {
    "worker-heartbeat": {"task": "default.heartbeat", "schedule": 30.0, "args": ("default",)},
    "publishing-tick": {"task": "default.publishing_tick", "schedule": 60.0},
    "recover-stale": {"task": "default.recover_stale", "schedule": 300.0},
    "nightly-backup": {"task": "default.backup", "schedule": crontab(hour=3, minute=15)},
}
