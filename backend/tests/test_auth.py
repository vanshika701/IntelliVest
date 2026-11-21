"""Integration tests for registration, login, and the /me endpoint —
exercises the full route -> service -> repository -> DB stack."""

from fastapi.testclient import TestClient


def _register(client: TestClient, email: str = "test@example.com", password: str = "password123"):
    return client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": password, "full_name": "Test User"},
    )


def test_register_creates_a_user_and_never_returns_the_password(client: TestClient) -> None:
    response = _register(client)

    assert response.status_code == 201
    body = response.json()
    assert body["email"] == "test@example.com"
    assert body["full_name"] == "Test User"
    assert "password" not in body
    assert "hashed_password" not in body


def test_register_rejects_a_duplicate_email(client: TestClient) -> None:
    _register(client)
    response = _register(client)

    assert response.status_code == 409


def test_login_succeeds_with_correct_credentials_and_returns_a_bearer_token(
    client: TestClient,
) -> None:
    _register(client)

    response = client.post(
        "/api/v1/auth/login",
        json={"email": "test@example.com", "password": "password123"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer"
    assert len(body["access_token"]) > 20


def test_login_rejects_wrong_password(client: TestClient) -> None:
    _register(client)

    response = client.post(
        "/api/v1/auth/login",
        json={"email": "test@example.com", "password": "wrong-password"},
    )

    assert response.status_code == 401


def test_me_returns_the_current_user_given_a_valid_token(client: TestClient) -> None:
    _register(client)
    login = client.post(
        "/api/v1/auth/login",
        json={"email": "test@example.com", "password": "password123"},
    )
    token = login.json()["access_token"]

    response = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    assert response.json()["email"] == "test@example.com"


def test_me_rejects_a_missing_or_invalid_token(client: TestClient) -> None:
    no_token = client.get("/api/v1/auth/me")
    assert no_token.status_code in (401, 403)  # HTTPBearer returns 403 when no header at all

    bad_token = client.get("/api/v1/auth/me", headers={"Authorization": "Bearer not-a-real-token"})
    assert bad_token.status_code == 401
