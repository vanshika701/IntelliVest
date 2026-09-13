"""Integration test — exercises the full route -> service -> DB stack."""

from fastapi.testclient import TestClient


def test_health_endpoint_returns_status_and_database_fields(client: TestClient) -> None:
    response = client.get("/api/v1/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] in {"ok", "degraded"}
    assert body["database"] in {"connected", "unavailable"}
