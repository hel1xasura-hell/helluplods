import uuid

from app.models import Owner, Project
from tests.conftest import auth


def test_create_list_delete_project(client):
    r = client.post("/api/projects", json={"name": "Canva tutorial"}, headers=auth())
    assert r.status_code == 201
    pid = r.json()["id"]
    assert [p["id"] for p in client.get("/api/projects", headers=auth()).json()] == [pid]
    assert client.delete(f"/api/projects/{pid}", headers=auth()).status_code == 204
    assert client.get(f"/api/projects/{pid}", headers=auth()).status_code == 404


def test_project_validation(client):
    assert client.post("/api/projects", json={"name": ""}, headers=auth()).status_code == 422
    bad = {"name": "x", "publishing_mode": "yolo"}
    assert client.post("/api/projects", json=bad, headers=auth()).status_code == 422


def test_cannot_access_project_of_another_owner(client, db_session):
    client.get("/api/me", headers=auth())  # initialise owner
    other = Owner(firebase_uid="other", email="other@example.com")
    db_session.add(other)
    db_session.flush()
    foreign = Project(owner_id=other.id, name="secret")
    db_session.add(foreign)
    db_session.commit()
    assert client.get(f"/api/projects/{foreign.id}", headers=auth()).status_code == 404
    assert client.delete(f"/api/projects/{foreign.id}", headers=auth()).status_code == 404
    assert client.post(f"/api/projects/{foreign.id}/targets",
                       json={"kind": "website_name", "value": "x"}, headers=auth()).status_code == 404
    assert client.get("/api/projects", headers=auth()).json() == []


def test_unknown_project_404(client):
    assert client.get(f"/api/projects/{uuid.uuid4()}", headers=auth()).status_code == 404


def test_target_ssrf_blocked(client):
    pid = client.post("/api/projects", json={"name": "p"}, headers=auth()).json()["id"]
    for url in ["http://127.0.0.1:8000", "http://169.254.169.254/latest/meta-data", "file:///etc/passwd"]:
        r = client.post(f"/api/projects/{pid}/targets", json={"kind": "website_url", "value": url}, headers=auth())
        assert r.status_code == 422, url


def test_website_name_target_accepted(client):
    pid = client.post("/api/projects", json={"name": "p"}, headers=auth()).json()["id"]
    r = client.post(f"/api/projects/{pid}/targets", json={"kind": "android_app", "value": "Notion"}, headers=auth())
    assert r.status_code == 201 and r.json()["status"] == "pending"


def test_foreign_origin_blocked(client):
    r = client.post("/api/projects", json={"name": "p"}, headers={**auth(), "Origin": "https://evil.example"})
    assert r.status_code == 403
