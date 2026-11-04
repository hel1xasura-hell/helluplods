from datetime import datetime, timedelta, timezone

import pytest

from app.api.routes import devices as devices_routes
from app.models import Device, DevicePairingCode, DeviceTask, Owner, Project, ResearchTarget
from tests.conftest import WEBM, auth


@pytest.fixture(autouse=True)
def reset_throttle():
    devices_routes._attempts.clear()


def pair(client, name="My PC", platform="windows"):
    code = client.post("/api/devices/pairing-codes", headers=auth()).json()["code"]
    r = client.post("/api/devices/pair", json={"code": code, "name": name, "platform": platform})
    assert r.status_code == 201, r.text
    return r.json(), code


def dev_headers(cred):
    return {"Authorization": f"Device {cred}"}


def make_target(client, mode="cloud", url="https://acme.example/"):
    pid = client.post("/api/projects", json={"name": "p", "execution_mode": mode}, headers=auth()).json()["id"]
    tid = client.post(f"/api/projects/{pid}/targets", json={"kind": "website_url", "value": url},
                      headers=auth()).json()["id"]
    return pid, tid


# ---- pairing ----
def test_pairing_code_is_single_use_and_credential_is_hashed(client, db_session):
    res, code = pair(client)
    assert res["credential"].startswith("hud_")
    again = client.post("/api/devices/pair", json={"code": code, "name": "x", "platform": "linux"})
    assert again.status_code == 400
    device = db_session.query(Device).one()
    assert device.credential_hash != res["credential"] and len(device.credential_hash) == 64
    assert db_session.query(DevicePairingCode).one().code_hash != code


def test_wrong_and_expired_codes_rejected(client, db_session):
    assert client.post("/api/devices/pair", json={"code": "WRONGCODE1", "name": "x", "platform": "linux"}).status_code == 400
    code = client.post("/api/devices/pairing-codes", headers=auth()).json()["code"]
    row = db_session.query(DevicePairingCode).one()
    row.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
    db_session.commit()
    assert client.post("/api/devices/pair", json={"code": code, "name": "x", "platform": "linux"}).status_code == 400


def test_pairing_requires_owner_to_create_code_and_validates_platform(client):
    assert client.post("/api/devices/pairing-codes").status_code == 401
    code = client.post("/api/devices/pairing-codes", headers=auth()).json()["code"]
    assert client.post("/api/devices/pair", json={"code": code, "name": "x", "platform": "amiga"}).status_code == 422


def test_pairing_attempts_are_throttled(client):
    codes = [client.post("/api/devices/pair", json={"code": f"BAD{i}CODE12", "name": "x", "platform": "linux"}).status_code
             for i in range(10)]
    assert codes[:8] == [400] * 8 and codes[8:] == [429, 429]


# ---- device auth / revocation ----
def test_device_endpoints_require_valid_credential(client):
    for path in ("/api/device/heartbeat", "/api/device/tasks/claim"):
        assert client.post(path).status_code == 401
        assert client.post(path, headers=dev_headers("hud_nope")).status_code == 401
    assert client.post("/api/device/heartbeat", headers=auth()).status_code == 401  # owner token is not a device


def test_heartbeat_marks_online_and_revoke_locks_out(client):
    res, _ = pair(client)
    assert client.post("/api/device/heartbeat", headers=dev_headers(res["credential"])).status_code == 204
    dev = client.get("/api/devices", headers=auth()).json()[0]
    assert dev["online"] is True and dev["revoked"] is False
    assert client.delete(f"/api/devices/{dev['id']}", headers=auth()).status_code == 204
    assert client.post("/api/device/heartbeat", headers=dev_headers(res["credential"])).status_code == 401
    assert client.get("/api/devices", headers=auth()).json()[0]["revoked"] is True
    assert client.get("/api/dashboard", headers=auth()).json()["local_workers"] == 0


# ---- executor assignment ----
def test_cloud_mode_records_in_cloud(client):
    _, tid = make_target(client, "cloud")
    r = client.post(f"/api/targets/{tid}/record", json={}, headers=auth())
    assert r.status_code == 202 and r.json()["executor"] == "cloud"
    recs = client.get("/api/recordings", headers=auth()).json()
    assert len(recs) == 1 and recs[0]["executor"] == "cloud" and recs[0]["is_real_capture"] is True
    assert recs[0]["duration_seconds"] == 8.5
    file = client.get(f"/api/recordings/{recs[0]['id']}/file", headers=auth())
    assert file.status_code == 200 and file.content == WEBM and file.headers["content-type"] == "video/webm"


def test_local_mode_without_device_is_refused_not_faked(client):
    _, tid = make_target(client, "local")
    r = client.post(f"/api/targets/{tid}/record", json={}, headers=auth())
    assert r.status_code == 409 and "no paired device" in r.json()["detail"]
    assert client.get("/api/recordings", headers=auth()).json() == []


def test_both_mode_assigns_exactly_one_executor(client):
    _, tid = make_target(client, "both")
    first = client.post(f"/api/targets/{tid}/record", json={}, headers=auth()).json()
    assert first["executor"] == "cloud"                           # no device online -> cloud
    assert client.post(f"/api/targets/{tid}/record", json={}, headers=auth()).status_code in (202,)  # first finished
    res, _ = pair(client)
    client.post("/api/device/heartbeat", headers=dev_headers(res["credential"]))
    _, tid2 = make_target(client, "both", "https://other.example/")
    second = client.post(f"/api/targets/{tid2}/record", json={}, headers=auth()).json()
    assert second["executor"] == "local"                          # device online -> local, never both
    assert client.post(f"/api/targets/{tid2}/record", json={}, headers=auth()).status_code == 409  # no duplicate
    assert db_count(client, tid2) == 1


def db_count(client, tid):
    tasks = client.get("/api/recording-tasks", headers=auth()).json()
    return len([t for t in tasks if t["status"] in ("queued", "claimed") and t["executor"] == "local"])


def test_private_target_url_cannot_be_recorded(client, db_session):
    client.get("/api/me", headers=auth())
    owner = db_session.query(Owner).one()
    proj = Project(owner_id=owner.id, name="p")
    db_session.add(proj); db_session.flush()
    t = ResearchTarget(project_id=proj.id, kind="website_url", value="http://169.254.169.254/")
    db_session.add(t); db_session.commit()
    assert client.post(f"/api/targets/{t.id}/record", json={}, headers=auth()).status_code == 422


# ---- local device full flow ----
def test_device_claims_uploads_and_completes(client):
    res, _ = pair(client)
    h = dev_headers(res["credential"])
    client.post("/api/device/heartbeat", headers=h)
    _, tid = make_target(client, "local")
    assert client.post(f"/api/targets/{tid}/record", json={"duration_seconds": 5}, headers=auth()).json()["executor"] == "local"
    task = client.post("/api/device/tasks/claim", headers=h).json()["task"]
    assert task["url"] == "https://acme.example/" and task["duration_seconds"] == 5
    assert client.post("/api/device/tasks/claim", headers=h).json()["task"] is None   # no double claim

    assert client.post(f"/api/device/tasks/{task['id']}/complete", json={}, headers=h).status_code == 409  # no file yet
    bad = client.put(f"/api/device/tasks/{task['id']}/file", content=b"<html>not a video</html>", headers=h)
    assert bad.status_code == 422
    ok = client.put(f"/api/device/tasks/{task['id']}/file", content=WEBM, headers=h)
    assert ok.status_code == 200
    done = client.post(f"/api/device/tasks/{task['id']}/complete", headers=h,
                       json={"duration_seconds": 7.2, "width": 1280, "height": 720, "final_url": "https://acme.example/",
                             "actions": [{"t": 0.1, "type": "scroll", "y": 100}]})
    assert done.status_code == 200
    rec = client.get("/api/recordings", headers=auth()).json()[0]
    assert rec["executor"] == "local" and rec["duration_seconds"] == 7.2
    part = client.get(f"/api/recordings/{rec['id']}/file", headers={**auth(), "Range": "bytes=0-3"})
    assert part.status_code == 206 and part.content == WEBM[:4]
    assert client.get(f"/api/recordings/{rec['id']}/file", headers={**auth(), "Range": "bytes=9999999-"}).status_code == 416


def test_device_cannot_touch_other_devices_or_owners_tasks(client, db_session):
    res, _ = pair(client)
    h = dev_headers(res["credential"])
    client.post("/api/device/heartbeat", headers=h)
    other = Owner(firebase_uid="oz", email="oz@example.com")
    db_session.add(other); db_session.flush()
    proj = Project(owner_id=other.id, name="theirs")
    db_session.add(proj); db_session.flush()
    foreign = DeviceTask(project_id=proj.id, kind="record", executor="local", payload={"url": "https://x.example"})
    db_session.add(foreign); db_session.commit()
    assert client.post("/api/device/tasks/claim", headers=h).json()["task"] is None
    assert client.put(f"/api/device/tasks/{foreign.id}/file", content=WEBM, headers=h).status_code == 404
    assert client.post(f"/api/device/tasks/{foreign.id}/fail", json={"error": "x"}, headers=h).status_code == 404


def test_device_failure_is_recorded(client):
    res, _ = pair(client)
    h = dev_headers(res["credential"])
    client.post("/api/device/heartbeat", headers=h)
    _, tid = make_target(client, "local")
    client.post(f"/api/targets/{tid}/record", json={}, headers=auth())
    task = client.post("/api/device/tasks/claim", headers=h).json()["task"]
    assert client.post(f"/api/device/tasks/{task['id']}/fail", json={"error": "robots.txt disallows"}, headers=h).status_code == 204
    t = client.get("/api/recording-tasks", headers=auth()).json()[0]
    assert t["status"] == "failed" and "robots" in t["error"]


def test_recordings_are_private(client, db_session):
    import uuid
    assert client.get("/api/recordings").status_code == 401
    assert client.get(f"/api/recordings/{uuid.uuid4()}/file", headers=auth()).status_code == 404
