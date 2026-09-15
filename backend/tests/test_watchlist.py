"""Integration tests for the watchlist module — add/list/update/remove,
plus price enrichment from real ingested market data.
"""

from datetime import UTC, datetime

import pymongo
from fastapi.testclient import TestClient

from app.core.config import settings


def test_add_and_list_watchlist_item(client: TestClient, auth_headers: dict[str, str]) -> None:
    response = client.post(
        "/api/v1/watchlist",
        headers=auth_headers,
        json={"ticker": "RELIANCE.NS", "notes": "Long-term hold"},
    )
    assert response.status_code == 201

    listed = client.get("/api/v1/watchlist", headers=auth_headers).json()
    assert len(listed) == 1
    assert listed[0]["ticker"] == "RELIANCE.NS"
    assert listed[0]["notes"] == "Long-term hold"
    assert listed[0]["priority"] == "medium"  # default


def test_adding_the_same_ticker_twice_is_rejected(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    client.post("/api/v1/watchlist", headers=auth_headers, json={"ticker": "TCS.NS"})
    response = client.post("/api/v1/watchlist", headers=auth_headers, json={"ticker": "TCS.NS"})

    assert response.status_code == 409


def test_watchlist_enriches_with_latest_price(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    # Insert fake price history via a plain sync pymongo client (not
    # Motor) so this doesn't await anything on TestClient's own internal
    # event loop — writes land in the same DB since both point at the
    # same (test) mongodb_db_name.
    sync_db = pymongo.MongoClient(settings.mongodb_uri)[settings.mongodb_db_name]
    sync_db["prices"].insert_many(
        [
            {
                "ticker": "INFY.NS",
                "date": datetime(2026, 1, 1, tzinfo=UTC),
                "open": 100,
                "high": 105,
                "low": 99,
                "close": 100.0,
                "volume": 1000,
            },
            {
                "ticker": "INFY.NS",
                "date": datetime(2026, 1, 2, tzinfo=UTC),
                "open": 100,
                "high": 110,
                "low": 100,
                "close": 110.0,
                "volume": 1000,
            },
        ]
    )

    client.post("/api/v1/watchlist", headers=auth_headers, json={"ticker": "INFY.NS"})
    listed = client.get("/api/v1/watchlist", headers=auth_headers).json()

    item = listed[0]
    assert item["latest_price"] == 110.0
    assert item["previous_close"] == 100.0
    assert item["change_pct"] == 10.0


def test_patch_updates_notes_and_priority(client: TestClient, auth_headers: dict[str, str]) -> None:
    add_response = client.post("/api/v1/watchlist", headers=auth_headers, json={"ticker": "WIPRO.NS"})
    item_id = add_response.json()["id"]

    response = client.patch(
        f"/api/v1/watchlist/{item_id}",
        headers=auth_headers,
        json={"notes": "Watching for a dip", "priority": "high"},
    )
    assert response.status_code == 200

    listed = client.get("/api/v1/watchlist", headers=auth_headers).json()
    assert listed[0]["notes"] == "Watching for a dip"
    assert listed[0]["priority"] == "high"


def test_delete_removes_watchlist_item(client: TestClient, auth_headers: dict[str, str]) -> None:
    add_response = client.post("/api/v1/watchlist", headers=auth_headers, json={"ticker": "SBIN.NS"})
    item_id = add_response.json()["id"]

    response = client.delete(f"/api/v1/watchlist/{item_id}", headers=auth_headers)
    assert response.status_code == 204

    listed = client.get("/api/v1/watchlist", headers=auth_headers).json()
    assert listed == []
