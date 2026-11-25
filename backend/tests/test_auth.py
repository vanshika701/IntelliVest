"""Integration tests for registration, login, and the /me endpoint —
exercises the full route -> service -> repository -> DB stack."""

import pymongo
import pytest
from fastapi.testclient import TestClient

from app.core.config import settings


def _register(client: TestClient, email: str = "test@example.com", password: str = "password123"):
    return client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": password, "full_name": "Test User", "date_of_birth": "2000-05-17"},
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


def _reset(client: TestClient, dob: str = "2000-05-17", email: str = "test@example.com", password="new-password1"):
    return client.post(
        "/api/v1/auth/reset-password",
        json={"email": email, "date_of_birth": dob, "new_password": password},
    )


def _login(client: TestClient, password: str):
    return client.post("/api/v1/auth/login", json={"email": "test@example.com", "password": password})


@pytest.mark.parametrize("dob", [None, "not-a-date", "2999-01-01", "1850-01-01"])
def test_register_requires_a_plausible_date_of_birth(client: TestClient, dob) -> None:
    body = {"email": "a@example.com", "password": "password123", "full_name": "A", "date_of_birth": dob}
    assert client.post("/api/v1/auth/register", json=body).status_code == 422


def test_reset_password_with_the_right_date_of_birth(client: TestClient) -> None:
    _register(client)
    assert _reset(client, email="TEST@example.com").status_code == 204
    assert _login(client, "password123").status_code == 401
    assert _login(client, "new-password1").status_code == 200


def test_reset_gives_the_same_answer_for_wrong_date_and_unknown_email(client: TestClient) -> None:
    _register(client)
    wrong, unknown = _reset(client, "2000-05-18"), _reset(client, email="nobody@example.com")
    assert wrong.status_code == unknown.status_code == 400 and wrong.json() == unknown.json()
    assert _login(client, "password123").status_code == 200


def test_reset_rejects_short_and_over_long_passwords(client: TestClient) -> None:
    _register(client)
    assert _reset(client, password="short").status_code == 422
    assert _reset(client, password="\u20b9" * 30).status_code == 422  # 90 bytes


def test_reset_is_locked_after_five_attempts(client: TestClient) -> None:
    _register(client)
    for day in range(1, 6):
        assert _reset(client, f"1999-01-0{day}").status_code == 400
    assert _reset(client).status_code == 429  # even with the right date
    assert _login(client, "password123").status_code == 200


def test_old_account_can_add_its_date_of_birth_once(client: TestClient) -> None:
    _register(client)
    db = pymongo.MongoClient(settings.mongodb_uri)[settings.mongodb_db_name]
    db.users.update_one({}, {"$unset": {"date_of_birth": 1}})
    assert _reset(client).status_code == 400  # nothing to verify against

    headers = {"Authorization": f"Bearer {_login(client, 'password123').json()['access_token']}"}
    assert client.get("/api/v1/auth/me", headers=headers).json()["has_date_of_birth"] is False
    url, body = "/api/v1/auth/date-of-birth", {"date_of_birth": "2000-05-17"}
    assert client.put(url, json=body).status_code in (401, 403)
    assert client.put(url, headers=headers, json=body).status_code == 204
    assert client.put(url, headers=headers, json={"date_of_birth": "1990-01-01"}).status_code == 409
    me = client.get("/api/v1/auth/me", headers=headers).json()
    assert me["has_date_of_birth"] is True and "date_of_birth" not in me
    assert _reset(client).status_code == 204
