"""Integration tests for the sentiment API through the real HTTP layer."""

from fastapi.testclient import TestClient


def test_ticker_sentiment_requires_auth(client: TestClient) -> None:
    assert client.get("/api/v1/sentiment/TCS.NS").status_code == 401


def test_untracked_ticker_returns_404(client: TestClient, auth_headers: dict[str, str]) -> None:
    response = client.get("/api/v1/sentiment/NOTREAL.NS", headers=auth_headers)
    assert response.status_code == 404


def test_ticker_sentiment_returns_empty_summary_without_data(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    response = client.get("/api/v1/sentiment/tcs.ns", headers=auth_headers)
    assert response.status_code == 200
    body = response.json()
    assert body["ticker"] == "TCS.NS"
    assert body["article_count"] == 0
    assert body["overall_label"] is None


def test_universe_sentiment_lists_every_tracked_ticker(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    response = client.get("/api/v1/sentiment?days=30", headers=auth_headers)
    assert response.status_code == 200
    assert len(response.json()) == 20


def test_days_parameter_is_validated(client: TestClient, auth_headers: dict[str, str]) -> None:
    assert client.get("/api/v1/sentiment?days=0", headers=auth_headers).status_code == 422
