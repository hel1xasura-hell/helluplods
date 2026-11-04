from datetime import datetime, timedelta, timezone

from app.models import DeviceTask, Notification, Owner, Project, ResearchTarget, StorageObject, VideoRender
from app.services import maintenance
from tests.conftest import auth
from tests.test_stage5_api import approve, connect, make_ready_render, pending


# ---- health / security / audit ----
def test_system_health_reports_components_and_stuck_work(client, db_session):
    h = client.get("/api/system/health", headers=auth()).json()
    names = {c["name"]: c["status"] for c in h["components"]}
    assert names["database"] == "ok" and names["redis"] == "ok" and names["storage"] == "ok"
    assert h["queue_depth"] == {"default": 0, "browser": 0, "render": 0} and h["overall"] == "ok" and h["stuck"]["renders"] == 0


def test_stuck_render_is_detected_and_recovered(client, db_session, stage4_holder):
    pid, sid, rid = make_ready_render(client, stage4_holder)
    import uuid
    r = db_session.get(VideoRender, uuid.UUID(rid))
    r.status, r.updated_at = "rendering", datetime.now(timezone.utc) - timedelta(hours=2)
    db_session.commit()
    assert client.get("/api/system/health", headers=auth()).json()["stuck"]["renders"] == 1
    assert client.post("/api/system/recover", headers=auth()).json()["renders"] == 1
    db_session.refresh(r)
    assert r.status == "failed" and "Render again" in r.error


def test_recovery_fails_stale_uploads_tasks_and_research(client, db_session, stage4_holder):
    client.get("/api/me", headers=auth())
    owner = db_session.query(Owner).one()
    proj = Project(owner_id=owner.id, name="p")
    db_session.add(proj); db_session.flush()
    old = datetime.now(timezone.utc) - timedelta(hours=5)
    t = ResearchTarget(project_id=proj.id, kind="website_url", value="https://x.example", status="running")
    task = DeviceTask(project_id=proj.id, kind="record", executor="local", status="claimed", payload={}, claimed_at=old)
    db_session.add_all([t, task]); db_session.commit()
    t.updated_at = old
    db_session.commit()
    counts = maintenance.recover_stale(db_session)
    assert counts["research"] == 1 and counts["device_tasks"] == 1
    assert db_session.query(Notification).filter_by(title="Recovered stuck work").count() == 1
    assert maintenance.recover_stale(db_session) == {"renders": 0, "uploads": 0, "device_tasks": 0, "cloud_tasks": 0, "research": 0}


def test_security_checks_endpoint(client):
    checks = {c["name"]: c["status"] for c in client.get("/api/security/checks", headers=auth()).json()}
    assert checks["owner_email"] == "pass" and checks["cors_not_wildcard"] == "pass" and checks["durable_jobs"] == "warn"
    assert client.get("/api/security/checks").status_code == 401


def test_audit_log_is_owner_scoped_and_filterable(client):
    client.post("/api/projects", json={"name": "p"}, headers=auth())
    all_events = client.get("/api/audit", headers=auth()).json()
    assert any(e["action"] == "project.created" for e in all_events)
    only = client.get("/api/audit?action=project.", headers=auth()).json()
    assert only and all(e["action"].startswith("project.") for e in only)
    assert client.get("/api/audit?before=notadate", headers=auth()).status_code == 422
    assert client.get("/api/audit").status_code == 401


# ---- backups ----
def test_backup_creates_verifies_and_applies_retention(client, db_session, tmp_path):
    from app.services.storage import LocalStorage
    client.get("/api/me", headers=auth())
    owner = db_session.query(Owner).one()
    store = LocalStorage(str(tmp_path))
    t0 = datetime.now(timezone.utc)
    dump = lambda a: b"PGDMP" + b"x" * 20  # noqa: E731
    first = maintenance.run_backup(db_session, owner.id, store, "postgresql://u:p@h/d", runner=dump, keep=1, keep_days=0, now=t0)
    assert store.get(first.key).startswith(b"PGDMP") and first.sha256
    second = maintenance.run_backup(db_session, owner.id, store, "postgresql://u:p@h/d", runner=dump, keep=1, keep_days=0,
                                    now=t0 + timedelta(days=1))
    kept = db_session.query(StorageObject).filter(StorageObject.key.like("%/backups/%")).all()
    assert [o.id for o in kept] == [second.id]                       # the older one was removed, the newest is never deleted
    try:
        store.get(first.key); assert False, "old backup file should be deleted"
    except FileNotFoundError:
        pass
    try:
        maintenance.run_backup(db_session, owner.id, store, "postgresql://u:p@h/d", runner=lambda a: b"not a dump")
        assert False, "invalid dumps must be rejected"
    except RuntimeError as exc:
        assert "valid PostgreSQL archive" in str(exc)
    assert db_session.query(Notification).filter_by(title="Backup failed").count() == 1
    assert len(kept) == 1 and "backups" in kept[0].key


def test_backup_endpoints_are_honest_without_postgres(client):
    listing = client.get("/api/backups", headers=auth()).json()
    assert listing["database_is_postgres"] is False and listing["items"] == []
    assert client.post("/api/backups", headers=auth()).status_code == 409
    assert client.get("/api/backups").status_code == 401


# ---- analytics ----
def test_production_analytics_reflect_real_records(client, yt, stage4_holder):
    acct = connect(client, yt)
    make_ready_render(client, stage4_holder, title="One")
    approve(client, pending(client)[0]["id"], acct)
    make_ready_render(client, stage4_holder, title="Two")
    a = client.get("/api/analytics/production?days=7", headers=auth()).json()
    assert a["totals"]["renders"] == 2 and a["totals"]["renders_ready"] == 2 and a["totals"]["uploads"] == 1
    assert a["render_success_rate"] == 1.0 and a["upload_success_rate"] == 1.0 and len(a["renders_per_day"]) == 7
    assert a["approval_funnel"]["approved"] == 1 and a["approval_funnel"]["pending"] == 1
    assert a["target_per_day"] == 50 and a["progress_toward_target"] == round(1 / (50 * 7), 3)
    assert client.get("/api/analytics/production").status_code == 401


def test_youtube_stats_sync_and_totals(client, yt, stage4_holder):
    assert client.post("/api/analytics/youtube/sync", headers=auth()).status_code == 409  # no channel yet
    acct = connect(client, yt)
    make_ready_render(client, stage4_holder)
    approve(client, pending(client)[0]["id"], acct)
    assert client.get("/api/analytics/youtube", headers=auth()).json()["videos"][0]["views"] is None
    assert client.post("/api/analytics/youtube/sync", headers=auth()).json() == {"synced": 1}
    got = client.get("/api/analytics/youtube", headers=auth()).json()
    assert got["videos"][0]["views"] == 100 and got["totals"] == {"views": 100, "likes": 7, "comments": 2}
