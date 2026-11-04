"""The whole pipeline through the real API, with fakes only at the external edges (browser, FFmpeg render, YouTube).
Owner login -> project -> target -> research -> recording -> script -> thumbnail -> render -> approval -> upload -> analytics."""
from tests.conftest import WEBM, auth
from tests.test_stage5_api import PASS_ALL


def test_full_owner_journey(client, yt, stage4_holder, db_session):
    assert client.get("/api/me", headers=auth()).json()["email"] == "owner@example.com"           # owner login
    pid = client.post("/api/projects", json={"name": "Acme tutorial"}, headers=auth()).json()["id"]  # create project
    tid = client.post(f"/api/projects/{pid}/targets", json={"kind": "website_url", "value": "https://acme.example/"}, headers=auth()).json()["id"]
    assert client.post(f"/api/targets/{tid}/research", headers=auth()).status_code == 202       # research the website
    report = client.get(f"/api/targets/{tid}/report", headers=auth()).json()["body"]            # capture screenshots, report
    assert report["screenshot_ids"] and report["tested_hands_on"] is False
    assert client.post(f"/api/targets/{tid}/record", json={}, headers=auth()).status_code == 202  # record a demonstration
    rec = client.get("/api/recordings", headers=auth()).json()[0]
    assert rec["is_real_capture"] and client.get(f"/api/recordings/{rec['id']}/file", headers=auth()).content == WEBM

    sid = client.post(f"/api/projects/{pid}/scripts", json={"title": "Acme tutorial", "from_target_id": tid}, headers=auth()).json()["id"]
    scenes = client.get(f"/api/scripts/{sid}", headers=auth()).json()["scenes"]
    for sc in scenes[:3]:                                                                         # write the script
        client.patch(f"/api/scenes/{sc['id']}", json={"narration": f"Welcome to Acme basics, part {sc['position']}. " + "word " * 30,
                                                      "recording_id": rec["id"]}, headers=auth())
    client.put(f"/api/scripts/{sid}/metadata", json={"title": "Acme tutorial", "description": "Learn Acme basics", "tags": ["notes"]}, headers=auth())
    thumb = client.post(f"/api/projects/{pid}/thumbnails", json={"text": "Acme basics", "screenshot_id": report["screenshot_ids"][0]}, headers=auth()).json()["id"]
    client.post(f"/api/thumbnails/{thumb}/select", headers=auth())

    fake = stage4_holder["hooks"][0]
    stage4_holder["hooks"] = (fake, lambda r, st, sc: PASS_ALL)
    render = client.post(f"/api/scripts/{sid}/render", json={"aspect_ratio": "16:9"}, headers=auth()).json()   # render video
    assert client.get(f"/api/renders/{render['id']}", headers=auth()).json()["status"] == "ready"

    acct = client.post("/api/youtube/oauth/start", headers=auth()).json()["auth_url"].split("state=")[1].split("&")[0]
    client.get(f"/api/youtube/oauth/callback?code=abc&state={acct}", follow_redirects=False)
    account_id = client.get("/api/youtube/status", headers=auth()).json()["accounts"][0]["id"]
    ap = [a for a in client.get("/api/approvals", headers=auth()).json() if a["status"] == "pending"][0]  # owner review
    assert ap["thumbnail_id"] == thumb and ap["render"]["quality"]
    r = client.post(f"/api/approvals/{ap['id']}/approve", headers=auth(),
                    json={"account_id": account_id, "visibility": "private", "made_for_kids": False, "contains_synthetic_media": False})
    assert r.status_code == 202                                                                   # approve -> upload
    job = client.get("/api/uploads", headers=auth()).json()[0]
    assert job["status"] == "uploaded" and job["youtube_video_id"] == "VID123"
    assert ("thumbnail", "VID123") in yt.calls                                                    # thumbnail uploaded too
    assert client.post("/api/analytics/youtube/sync", headers=auth()).json() == {"synced": 1}     # analytics
    dash = client.get("/api/dashboard", headers=auth()).json()
    assert dash["total_projects"] == 1 and dash["videos_awaiting_approval"] == 0 and dash["failed_jobs"] == 0
    actions = {e["action"] for e in client.get("/api/audit", headers=auth()).json()}
    assert {"project.created", "research.started", "recording.requested", "render.requested", "youtube.connected", "approval.approved"} <= actions
