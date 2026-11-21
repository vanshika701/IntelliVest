"""Integration tests for price alerts — CRUD, toggle, and the rule
evaluation engine (both the pure predicate and the scheduled job it
backs).
"""

from datetime import UTC, datetime

from fastapi.testclient import TestClient

from app.data.collections import get_prices_collection
from app.services.alert_service import (
    _check_trigger,
    add_alert,
    evaluate_all_alerts,
    list_alerts,
)


def test_check_trigger_above() -> None:
    assert _check_trigger("above", current_price=150, target=140, threshold_pct=5) is True
    assert _check_trigger("above", current_price=130, target=140, threshold_pct=5) is False


def test_check_trigger_below() -> None:
    assert _check_trigger("below", current_price=130, target=140, threshold_pct=5) is True
    assert _check_trigger("below", current_price=150, target=140, threshold_pct=5) is False


def test_check_trigger_within_pct() -> None:
    # Target 100, within 5% means [95, 105]
    assert _check_trigger("within_pct", current_price=103, target=100, threshold_pct=5) is True
    assert _check_trigger("within_pct", current_price=110, target=100, threshold_pct=5) is False


def test_check_trigger_within_pct_guards_against_zero_target() -> None:
    assert _check_trigger("within_pct", current_price=10, target=0, threshold_pct=5) is False


def test_create_list_toggle_delete_alert(client: TestClient, auth_headers: dict[str, str]) -> None:
    create = client.post(
        "/api/v1/alerts",
        headers=auth_headers,
        json={"ticker": "RELIANCE.NS", "condition": "above", "target_price": 150},
    )
    assert create.status_code == 201
    alert_id = create.json()["id"]

    listed = client.get("/api/v1/alerts", headers=auth_headers).json()
    assert len(listed) == 1
    assert listed[0]["is_active"] is True
    assert listed[0]["triggered"] is False

    toggle = client.patch(
        f"/api/v1/alerts/{alert_id}/toggle",
        headers=auth_headers,
        params={"is_active": False},
    )
    assert toggle.status_code == 200
    assert toggle.json()["is_active"] is False

    delete = client.delete(f"/api/v1/alerts/{alert_id}", headers=auth_headers)
    assert delete.status_code == 204
    assert client.get("/api/v1/alerts", headers=auth_headers).json() == []


async def test_evaluate_all_alerts_triggers_and_persists(mongo_test_db) -> None:
    """End-to-end: seed a real price above an alert's target, run the same
    evaluator the scheduler calls, and confirm the alert flips to triggered.

    Uses mongo_test_db (direct async connection) rather than the client/
    TestClient fixture — this test awaits Motor calls directly, and mixing
    that with TestClient's own internal event loop is exactly the hazard
    Phase 1's repository tests were written to avoid.
    """
    await get_prices_collection().insert_one(
        {
            "ticker": "TITAN.NS",
            "date": datetime(2026, 1, 1, tzinfo=UTC),
            "open": 100,
            "high": 200,
            "low": 100,
            "close": 180.0,
            "volume": 1000,
        }
    )

    await add_alert("user-1", {"ticker": "TITAN.NS", "condition": "above", "target_price": 150, "threshold_pct": 5.0})

    triggered_count = await evaluate_all_alerts()
    assert triggered_count == 1

    alerts = await list_alerts("user-1")
    assert alerts[0]["triggered"] is True
    assert alerts[0]["triggered_at"] is not None
    assert alerts[0]["latest_price"] == 180.0
