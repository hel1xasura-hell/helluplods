from tests.conftest import auth


def test_missing_token_rejected(client):
    assert client.get("/api/me").status_code == 401


def test_invalid_token_rejected(client):
    assert client.get("/api/me", headers=auth("nope")).status_code == 401


def test_non_owner_forbidden(client):
    assert client.get("/api/me", headers=auth("stranger-token")).status_code == 403


def test_unverified_email_forbidden(client):
    assert client.get("/api/me", headers=auth("unverified-token")).status_code == 403


def test_owner_initialized_on_first_login(client):
    r = client.get("/api/me", headers=auth())
    assert r.status_code == 200 and r.json()["email"] == "owner@example.com"
    assert client.get("/api/me", headers=auth()).json()["id"] == r.json()["id"]


def test_second_identity_with_owner_email_rejected(client):
    assert client.get("/api/me", headers=auth()).status_code == 200
    assert client.get("/api/me", headers=auth("impostor-token")).status_code == 403


def test_client_cannot_claim_owner_via_headers(client):
    r = client.get("/api/me", headers={"X-Owner": "true", "X-Role": "admin"})
    assert r.status_code == 401
