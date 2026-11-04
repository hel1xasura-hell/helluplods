from tests.conftest import auth


def test_dashboard_counts_reflect_records(client):
    empty = client.get("/api/dashboard", headers=auth()).json()
    assert empty["total_projects"] == 0 and empty["research_tasks"] == 0
    pid = client.post("/api/projects", json={"name": "a"}, headers=auth()).json()["id"]
    client.post("/api/projects", json={"name": "b"}, headers=auth())
    client.post(f"/api/projects/{pid}/targets", json={"kind": "website_name", "value": "Figma"}, headers=auth())
    data = client.get("/api/dashboard", headers=auth()).json()
    assert data["total_projects"] == 2 and data["research_tasks"] == 1
    assert data["cloud_workers"] == "not_connected"
    assert any(a["action"] == "project.created" for a in data["recent_activity"])


def test_dashboard_requires_auth(client):
    assert client.get("/api/dashboard").status_code == 401


def test_agents_listed_with_honest_status(client):
    agents = client.get("/api/agents", headers=auth()).json()
    assert len(agents) == 16 and not any(a["implemented"] for a in agents)


def test_integrations_report_missing_credentials(client):
    items = {i["key"]: i for i in client.get("/api/integrations", headers=auth()).json()}
    assert items["anthropic"]["configured"] is False
    assert "ANTHROPIC_API_KEY" in items["anthropic"]["missing"]


def test_health(client):
    assert client.get("/health/live").status_code == 200
    assert client.get("/health/ready").json()["database"] == "ok"
