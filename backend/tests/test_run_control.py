import pytest
from starlette.websockets import WebSocketDisconnect

from app.models import AgentRun, Owner, Project, ResearchReport, ResearchTarget
from app.services.research import run_research
from app.services.storage import LocalStorage
from tests.conftest import auth, make_capture


def _make_running_run(client, db_session, status="running"):
    pid = client.post("/api/projects", json={"name": "p"}, headers=auth()).json()["id"]
    run = AgentRun(project_id=pid, agent_key="research", status=status, input={})
    db_session.add(run)
    db_session.commit()
    return run


def test_pause_resume_stop_flow(client, db_session):
    run = _make_running_run(client, db_session)
    r = client.post(f"/api/runs/{run.id}/pause", headers=auth())
    assert r.status_code == 200 and r.json()["control"] == "pause"
    assert client.post(f"/api/runs/{run.id}/resume", headers=auth()).json()["control"] is None
    assert client.post(f"/api/runs/{run.id}/resume", headers=auth()).status_code == 409  # not paused
    assert client.post(f"/api/runs/{run.id}/stop", headers=auth()).json()["control"] == "stop"


def test_cannot_control_finished_or_foreign_runs(client, db_session):
    done = _make_running_run(client, db_session, status="succeeded")
    assert client.post(f"/api/runs/{done.id}/stop", headers=auth()).status_code == 409
    other = Owner(firebase_uid="o9", email="o9@example.com")
    db_session.add(other)
    db_session.flush()
    proj = Project(owner_id=other.id, name="x")
    db_session.add(proj)
    db_session.flush()
    foreign = AgentRun(project_id=proj.id, agent_key="research", status="running", input={})
    db_session.add(foreign)
    db_session.commit()
    for action in ("pause", "resume", "stop"):
        assert client.post(f"/api/runs/{foreign.id}/{action}", headers=auth()).status_code == 404
    assert client.post(f"/api/runs/{foreign.id}/stop").status_code == 401


def test_stop_midway_keeps_partial_report_and_says_so(db_session, session_factory, tmp_path):
    owner = Owner(firebase_uid="u", email="owner@example.com")
    db_session.add(owner)
    db_session.flush()
    proj = Project(owner_id=owner.id, name="p")
    db_session.add(proj)
    db_session.flush()
    target = ResearchTarget(project_id=proj.id, kind="website_url", value="https://acme.example/")
    db_session.add(target)
    db_session.commit()

    async def capture(url, on_page=None):
        c1 = make_capture(requested_url=url, final_url=url)
        c2 = make_capture(requested_url=url, final_url="https://acme.example/pricing", title="Pricing")
        assert await on_page(c1, 1, 3) is True
        with session_factory() as other:  # the owner presses Stop from another request
            run = other.query(AgentRun).filter_by(agent_key="research").one()
            run.control = "stop"
            other.commit()
        assert await on_page(c2, 2, 3) is False
        return [c1, c2]

    run_research(db_session, target.id, LocalStorage(str(tmp_path)), capture)
    run = db_session.query(AgentRun).filter_by(agent_key="research").one()
    db_session.refresh(run)
    assert run.status == "cancelled" and run.control is None
    report = db_session.query(ResearchReport).one()
    assert any("stopped" in l for l in report.body["limitations"])
    assert len(report.body["pages_explored"]) == 2


def test_progress_and_current_url_recorded(db_session, session_factory, tmp_path):
    owner = Owner(firebase_uid="u2", email="owner@example.com")
    db_session.add(owner)
    db_session.flush()
    proj = Project(owner_id=owner.id, name="p")
    db_session.add(proj)
    db_session.flush()
    target = ResearchTarget(project_id=proj.id, kind="website_url", value="https://acme.example/")
    db_session.add(target)
    db_session.commit()
    seen = {}

    async def capture(url, on_page=None):
        cap = make_capture(requested_url=url, final_url=url)
        await on_page(cap, 1, 2)
        with session_factory() as other:
            r = other.query(AgentRun).one()
            seen["progress"], seen["url"] = r.progress, r.current_url
        return [cap]

    run_research(db_session, target.id, LocalStorage(str(tmp_path)), capture)
    assert seen["url"] == "https://acme.example/" and 0 < seen["progress"] <= 0.9


def test_websocket_requires_valid_token_and_streams_runs(client, db_session):
    _make_running_run(client, db_session)
    with client.websocket_connect("/ws/runs") as ws:
        ws.send_text('{"token": "owner-token"}')
        data = ws.receive_json()
        assert data["runs"][0]["status"] == "running"
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect("/ws/runs") as ws:
            ws.send_text('{"token": "stranger-token"}')
            ws.receive_json()
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect("/ws/runs", headers={"origin": "https://evil.example"}) as ws:
            ws.receive_json()


def test_claim_checks_in_report(client):
    pid = client.post("/api/projects", json={"name": "p"}, headers=auth()).json()["id"]
    tid = client.post(f"/api/projects/{pid}/targets", json={"kind": "website_url", "value": "https://acme.example/"},
                      headers=auth()).json()["id"]
    client.post(f"/api/targets/{tid}/research", headers=auth())
    checks = client.get(f"/api/targets/{tid}/report", headers=auth()).json()["body"]["claim_checks"]
    assert checks[0]["proves_truth"] is False and checks[0]["method"] == "text_match"
