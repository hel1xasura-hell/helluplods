from datetime import datetime, timedelta, timezone

from app.integrations import youtube_logic as yl
from app.models import AudioAsset, Owner, Project, Scene, Script, UploadJob, YouTubeAccount
from app.services.render_service import narration_hash
from tests.conftest import auth

PASS_ALL = [{"name": n, "status": "pass", "detail": "ok"} for n in ("video_stream", "audio_stream", "resolution", "real_footage", "narration")]
GOOD = {"made_for_kids": False, "contains_synthetic_media": True, "visibility": "private", "daily_limit": 3}


def connect(client, yt):
    start = client.post("/api/youtube/oauth/start", headers=auth()).json()["auth_url"]
    state = start.split("state=")[1].split("&")[0]
    r = client.get(f"/api/youtube/oauth/callback?code=abc&state={state}", follow_redirects=False)
    assert r.status_code in (302, 307) and "connected=1" in r.headers["location"], r.headers.get("location")
    return client.get("/api/youtube/status", headers=auth()).json()["accounts"][0]["id"]


def make_ready_render(client, stage4_holder, title="Acme tutorial", mode="approval", scenes=3, quality=None, db=None):
    pid = client.post("/api/projects", json={"name": title + " proj", "publishing_mode": mode}, headers=auth()).json()["id"]
    sid = client.post(f"/api/projects/{pid}/scripts", json={"title": title}, headers=auth()).json()["id"]
    for i in range(scenes):
        client.post(f"/api/scripts/{sid}/scenes", json={"narration": f"Welcome to Acme basics part {i}. " + "word " * 30, "title": f"Part {i}"}, headers=auth())
    client.put(f"/api/scripts/{sid}/metadata", json={"title": title, "description": "Learn Acme basics", "tags": ["notes"]}, headers=auth())
    fake = stage4_holder["hooks"][0]
    q = PASS_ALL if quality is None else quality
    stage4_holder["hooks"] = (fake, lambda r, st, sc: q)
    job = client.post(f"/api/scripts/{sid}/render", json={}, headers=auth()).json()
    return pid, sid, job["id"]


def pending(client):
    return [a for a in client.get("/api/approvals", headers=auth()).json() if a["status"] == "pending"]


def approve(client, ap_id, acct, **kw):
    body = {"account_id": acct, "visibility": "private", "made_for_kids": False, "contains_synthetic_media": True, **kw}
    return client.post(f"/api/approvals/{ap_id}/approve", json=body, headers=auth())


# ---- connection ----
def test_status_is_honest_about_quota(client):
    st = client.get("/api/youtube/status", headers=auth()).json()
    assert st["configured"] is True and st["uploads_per_day_at_this_quota"] == 6 and "quota extension" in st["quota_note"]
    assert "PRIVATE" in st["audit_note"] and st["upload_cost_units"] == 1600
    assert not any(s.endswith("/auth/youtube") for s in st["scopes"])


def test_oauth_connect_stores_encrypted_refresh_token(client, yt, db_session):
    acct_id = connect(client, yt)
    row = db_session.get(YouTubeAccount, __import__("uuid").UUID(acct_id))
    assert row.channel_title == "My Channel" and yt.refresh_token not in row.refresh_token_encrypted and row.status == "connected"
    assert ("exchange", "abc", True) in yt.calls  # PKCE verifier was sent


def test_oauth_callback_rejects_bad_state_and_missing_refresh_token(client, yt):
    r = client.get("/api/youtube/oauth/callback?code=abc&state=forged", follow_redirects=False)
    assert "error=invalid_state" in r.headers["location"]
    assert "error=cancelled" in client.get("/api/youtube/oauth/callback?error=access_denied", follow_redirects=False).headers["location"]
    yt.refresh_token = None
    state = client.post("/api/youtube/oauth/start", headers=auth()).json()["auth_url"].split("state=")[1].split("&")[0]
    assert "no_refresh_token" in client.get(f"/api/youtube/oauth/callback?code=abc&state={state}", follow_redirects=False).headers["location"]


def test_oauth_start_requires_owner(client):
    assert client.post("/api/youtube/oauth/start").status_code == 401


def test_disconnect_clears_token_and_revokes(client, yt, db_session):
    acct_id = connect(client, yt)
    assert client.delete(f"/api/youtube/accounts/{acct_id}", headers=auth()).status_code == 204
    row = db_session.get(YouTubeAccount, __import__("uuid").UUID(acct_id))
    assert row.status == "disconnected" and row.refresh_token_encrypted == "" and ("revoke",) in yt.calls


# ---- defaults ----
def test_defaults_validation(client):
    assert client.put("/api/publishing/defaults", json={"visibility": "private"}, headers=auth()).status_code == 422  # explicit kids/synthetic answers required
    assert client.put("/api/publishing/defaults", json={**GOOD, "publish_hours_utc": [25]}, headers=auth()).status_code == 422
    assert client.put("/api/publishing/defaults", json={**GOOD, "publish_hours_utc": [14, 18]}, headers=auth()).status_code == 200
    assert client.get("/api/publishing/defaults", headers=auth()).json()["daily_limit"] == 3


# ---- approval -> upload ----
def test_ready_render_creates_pending_approval_with_quality_and_metadata(client, stage4_holder):
    make_ready_render(client, stage4_holder)
    ap = pending(client)[0]
    assert ap["metadata"]["title"] == "Acme tutorial" and ap["render"]["quality"][0]["name"] == "video_stream"
    assert client.get("/api/dashboard", headers=auth()).json()["videos_awaiting_approval"] == 1


def test_approve_uploads_privately_and_records_everything(client, yt, stage4_holder):
    acct = connect(client, yt)
    make_ready_render(client, stage4_holder)
    ap = pending(client)[0]
    r = approve(client, ap["id"], acct)
    assert r.status_code == 202
    job = client.get("/api/uploads", headers=auth()).json()[0]
    assert job["status"] == "uploaded" and job["youtube_video_id"] == "VID123" and job["progress"] == 1.0
    assert job["youtube_url"].endswith("VID123") and job["channel"] == "My Channel"
    assert any(c[0] == "start_upload" and c[1] == "private" for c in yt.calls)
    assert yt.resource["status"]["selfDeclaredMadeForKids"] is False and yt.resource["status"]["containsSyntheticMedia"] is True
    assert client.get("/api/youtube/status", headers=auth()).json()["accounts"][0]["quota_used_today"] >= 1600
    assert client.get("/api/approvals", headers=auth()).json()[0]["status"] == "approved"
    assert approve(client, ap["id"], acct).status_code == 409  # cannot approve twice


def test_approval_requires_explicit_kids_and_synthetic_answers(client, yt, stage4_holder):
    acct = connect(client, yt)
    make_ready_render(client, stage4_holder)
    ap = pending(client)[0]
    r = client.post(f"/api/approvals/{ap['id']}/approve", json={"account_id": acct, "visibility": "private"}, headers=auth())
    assert r.status_code == 422


def test_ai_voice_forces_synthetic_disclosure(client, yt, stage4_holder, db_session):
    acct = connect(client, yt)
    _, sid, _ = make_ready_render(client, stage4_holder, scenes=1)
    scene = db_session.query(Scene).filter_by(script_id=__import__("uuid").UUID(sid)).one()
    db_session.add(AudioAsset(project_id=db_session.get(Script, scene.script_id).project_id, scene_id=scene.id, source="tts",
                              provider="piper", text_hash=narration_hash(scene.narration), duration_seconds=3))
    db_session.commit()
    ap = pending(client)[0]
    r = approve(client, ap["id"], acct, contains_synthetic_media=False)
    assert r.status_code == 422 and "AI-generated" in r.json()["detail"]
    assert pending(client)[0]["uses_ai_voice"] is True
    assert approve(client, ap["id"], acct, contains_synthetic_media=True).status_code == 202


def test_scheduling_uses_private_plus_publish_at(client, yt, stage4_holder):
    acct = connect(client, yt)
    make_ready_render(client, stage4_holder)
    ap = pending(client)[0]
    soon = (datetime.now(timezone.utc) + timedelta(minutes=1)).isoformat()
    assert approve(client, ap["id"], acct, publish_at=soon).status_code == 422
    later = (datetime.now(timezone.utc) + timedelta(days=2)).isoformat()
    assert approve(client, ap["id"], acct, visibility="public", publish_at=later).status_code == 202
    job = client.get("/api/uploads", headers=auth()).json()[0]
    assert job["status"] == "scheduled" and job["publish_at"]
    assert yt.resource["status"]["privacyStatus"] == "private" and "publishAt" in yt.resource["status"]
    assert client.get("/api/publishing/calendar", headers=auth()).json()[0]["status"] == "scheduled"


def test_public_upload_is_marked_published(client, yt, stage4_holder):
    acct = connect(client, yt)
    make_ready_render(client, stage4_holder)
    approve(client, pending(client)[0]["id"], acct, visibility="public")
    assert client.get("/api/uploads", headers=auth()).json()[0]["status"] == "published"
    assert client.get("/api/dashboard", headers=auth()).json()["published_videos"] == 1


def test_duplicate_title_blocked(client, yt, stage4_holder):
    acct = connect(client, yt)
    make_ready_render(client, stage4_holder, title="Same title")
    approve(client, pending(client)[0]["id"], acct)
    make_ready_render(client, stage4_holder, title="Same title")
    r = approve(client, pending(client)[0]["id"], acct)
    assert r.status_code == 422 and "already uploaded" in r.json()["detail"]


def test_reject_flow(client, stage4_holder):
    make_ready_render(client, stage4_holder)
    ap = pending(client)[0]
    r = client.post(f"/api/approvals/{ap['id']}/reject", json={"note": "Needs a better intro"}, headers=auth())
    assert r.json()["status"] == "rejected" and r.json()["note"] == "Needs a better intro"
    assert client.post(f"/api/approvals/{ap['id']}/reject", json={}, headers=auth()).status_code == 409


# ---- resumable upload + recovery ----
def big_video(stage4_holder, size=5_000_000):
    def renderer(scenes, st, out, progress=None, should_stop=None, workdir=None):
        from app.media.ffmpeg_render import RenderResult
        out.write_bytes(b"\x00\x00\x00\x18ftypmp42" + b"\x00" * size)
        return RenderResult(out, 12.5, "1\n00:00:00,000 --> 00:00:02,000\nhi\n\n", "WEBVTT\n\n", [], [], [])
    stage4_holder["hooks"] = (renderer, stage4_holder["hooks"][1])


def test_retriable_chunk_errors_are_retried(client, yt, stage4_holder, monkeypatch):
    import time
    monkeypatch.setattr(time, "sleep", lambda s: None)
    acct = connect(client, yt)
    big_video(stage4_holder)
    make_ready_render(client, stage4_holder)
    yt.chunk_failures = 2
    approve(client, pending(client)[0]["id"], acct)
    assert client.get("/api/uploads", headers=auth()).json()[0]["status"] == "uploaded"
    assert sum(1 for c in yt.calls if c[0] == "start_upload") == 1


def test_failed_upload_resumes_without_restarting(client, yt, stage4_holder):
    acct = connect(client, yt)
    big_video(stage4_holder)
    make_ready_render(client, stage4_holder)
    yt.fatal_chunk_error = True
    approve(client, pending(client)[0]["id"], acct)
    job = client.get("/api/uploads", headers=auth()).json()[0]
    assert job["status"] == "failed" and "retry will resume" in job["error"]
    yt.fatal_chunk_error = None
    yt.stored = 2 * yl.CHUNK  # pretend YouTube kept the first two chunks
    assert client.post(f"/api/uploads/{job['id']}/retry", headers=auth()).status_code == 202
    done = client.get("/api/uploads", headers=auth()).json()[0]
    assert done["status"] == "uploaded"
    assert sum(1 for c in yt.calls if c[0] == "start_upload") == 1 and any(c[0] == "query" for c in yt.calls)
    after_query = yt.calls[[c[0] for c in yt.calls].index("query"):]
    assert min(c[1] for c in after_query if c[0] == "chunk") == 2 * yl.CHUNK
    assert client.post(f"/api/uploads/{job['id']}/retry", headers=auth()).status_code == 409  # only failed uploads


def test_revoked_google_access_asks_to_reconnect(client, yt, stage4_holder):
    acct = connect(client, yt)
    make_ready_render(client, stage4_holder)
    yt.refresh_error = True
    approve(client, pending(client)[0]["id"], acct)
    assert "Reconnect" in client.get("/api/uploads", headers=auth()).json()[0]["error"]
    assert client.get("/api/youtube/status", headers=auth()).json()["accounts"][0]["status"] == "reauthorize"
    make_ready_render(client, stage4_holder, title="Another")
    assert approve(client, pending(client)[0]["id"], acct).status_code == 409


def test_thumbnail_failure_does_not_fail_the_upload(client, yt, stage4_holder):
    acct = connect(client, yt)
    pid, _, _ = make_ready_render(client, stage4_holder)
    tid = client.post(f"/api/projects/{pid}/thumbnails", json={"text": "Acme"}, headers=auth()).json()["id"]
    client.post(f"/api/thumbnails/{tid}/select", headers=auth())
    yt.thumbnail_error = True
    approve(client, pending(client)[0]["id"], acct)
    job = client.get("/api/uploads", headers=auth()).json()[0]
    assert job["status"] == "uploaded" and any("Thumbnail was not set" in w for w in job["warnings"])


def test_daily_quota_blocks_new_uploads(client, yt, stage4_holder, db_session):
    acct = connect(client, yt)
    row = db_session.query(YouTubeAccount).one()
    row.quota_day, row.quota_used_today = yl.quota_day(), 9500
    db_session.commit()
    make_ready_render(client, stage4_holder)
    r = approve(client, pending(client)[0]["id"], acct)
    assert r.status_code == 429 and "quota" in r.json()["detail"].lower()


def test_channel_daily_upload_limit_has_a_clear_message(client, yt, stage4_holder):
    acct = connect(client, yt)
    make_ready_render(client, stage4_holder)

    async def limited(uri, data, start, total):
        from app.integrations.youtube_client import YouTubeError
        raise YouTubeError("The user has exceeded the number of videos they may upload.", 400, "uploadLimitExceeded")

    yt.upload_chunk = limited
    approve(client, pending(client)[0]["id"], acct)
    err = client.get("/api/uploads", headers=auth()).json()[0]["error"]
    assert "24-hour upload limit" in err and "separate from API quota" in err


def test_cancel_queued_upload(client, yt, stage4_holder, db_session):
    acct = connect(client, yt)
    make_ready_render(client, stage4_holder)
    ap = pending(client)[0]
    approve(client, ap["id"], acct)
    job = db_session.query(UploadJob).one()
    job.status = "queued"; db_session.commit()
    assert client.post(f"/api/uploads/{job.id}/cancel", headers=auth()).json()["status"] == "cancelled"
    assert client.post(f"/api/uploads/{job.id}/cancel", headers=auth()).status_code == 409


# ---- automatic mode ----
def test_automatic_mode_without_defaults_falls_back_to_review(client, yt, stage4_holder):
    connect(client, yt)
    make_ready_render(client, stage4_holder, mode="automatic")
    ap = pending(client)[0]
    assert "Needs your review" in ap["note"] and client.get("/api/uploads", headers=auth()).json() == []


def test_automatic_mode_without_channel_falls_back_to_review(client, stage4_holder):
    client.put("/api/publishing/defaults", json=GOOD, headers=auth())
    make_ready_render(client, stage4_holder, mode="automatic")
    assert "no YouTube channel" in pending(client)[0]["note"]


def test_automatic_mode_publishes_when_every_policy_passes(client, yt, stage4_holder):
    connect(client, yt)
    client.put("/api/publishing/defaults", json={**GOOD, "visibility": "unlisted"}, headers=auth())
    make_ready_render(client, stage4_holder, mode="automatic")
    jobs = client.get("/api/uploads", headers=auth()).json()
    assert len(jobs) == 1 and jobs[0]["visibility"] == "unlisted" and jobs[0]["status"] == "published"
    assert client.get("/api/approvals", headers=auth()).json()[0]["status"] == "auto_approved"


def test_automatic_mode_refuses_text_card_videos(client, yt, stage4_holder):
    connect(client, yt)
    client.put("/api/publishing/defaults", json=GOOD, headers=auth())
    weak = [{"name": "real_footage", "status": "warn", "detail": "text cards"}, {"name": "narration", "status": "pass", "detail": ""}]
    make_ready_render(client, stage4_holder, mode="automatic", quality=weak)
    assert "real footage" in pending(client)[0]["note"] and client.get("/api/uploads", headers=auth()).json() == []


def test_automatic_mode_respects_daily_limit(client, yt, stage4_holder):
    connect(client, yt)
    client.put("/api/publishing/defaults", json={**GOOD, "daily_limit": 1}, headers=auth())
    make_ready_render(client, stage4_holder, title="First", mode="automatic")
    make_ready_render(client, stage4_holder, title="Second", mode="automatic")
    assert len(client.get("/api/uploads", headers=auth()).json()) == 1
    assert "daily limit" in pending(client)[0]["note"].lower()


# ---- privacy ----
def test_endpoints_require_auth_and_are_private(client, yt, stage4_holder, db_session):
    import uuid
    for method, path in (("get", "/api/approvals"), ("get", "/api/uploads"), ("get", "/api/publishing/calendar"),
                         ("get", "/api/youtube/status"), ("put", "/api/publishing/defaults")):
        assert getattr(client, method)(path).status_code == 401, path
    assert client.post(f"/api/approvals/{uuid.uuid4()}/approve", json={}, headers=auth()).status_code in (404, 422)
    assert client.post(f"/api/uploads/{uuid.uuid4()}/cancel", headers=auth()).status_code == 404
    acct = connect(client, yt)
    other = Owner(firebase_uid="o7", email="o7@example.com")
    db_session.add(other); db_session.flush()
    proj = Project(owner_id=other.id, name="theirs")
    db_session.add(proj); db_session.commit()
    assert client.delete(f"/api/youtube/accounts/{uuid.uuid4()}", headers=auth()).status_code == 404
    assert acct
