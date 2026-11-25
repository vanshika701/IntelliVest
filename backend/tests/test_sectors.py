"""Phase 6 sector rollups: mapping, pure maths, storage and routes."""

from datetime import UTC, datetime, timedelta

from app.core.constants import SECTORS, STOCK_UNIVERSE
from app.data import sector_repository
from app.data.collections import get_news_collection, get_prices_collection
from app.services.sector_service import (
    build_snapshot,
    index_series,
    pct_change,
    refresh_sectors,
    trend_label,
)

NOW = datetime(2026, 11, 20, tzinfo=UTC)


def rows(closes, end=NOW):
    return [{"date": end - timedelta(days=len(closes) - 1 - i), "close": c} for i, c in enumerate(closes)]


def article(url, score, label="positive"):
    return {"url": url, "sentiment": {"score": score, "label": label}}


def test_every_tracked_stock_is_in_exactly_one_sector() -> None:
    mapped = [t for _, tickers in SECTORS.values() for t in tickers]
    assert sorted(mapped) == sorted(STOCK_UNIVERSE)


def test_pct_change_and_trend() -> None:
    assert pct_change([100, 110], 1) == 10
    assert pct_change([100], 1) is None
    assert [trend_label(x) for x in (2.1, -2.1, 2.0, None)] == ["up", "down", "flat", None]


def test_index_series_uses_common_dates_and_equal_weights() -> None:
    series = index_series([rows([100, 110, 120]), rows([1000, 1000])])
    assert [p["v"] for p in series] == [100, 104.55]  # (120/110 + 1) / 2


def test_snapshot_averages_stocks_and_counts_shared_story_once() -> None:
    shared = article("u1", 0.9)
    snap = build_snapshot(
        "it",
        "IT",
        {"TCS.NS": rows([100, 110]), "INFY.NS": rows([100, 96])},
        {"TCS.NS": [shared, article("u2", 0.0, "neutral")], "INFY.NS": [shared, article("u3", 0.6)]},
        NOW,
    )
    assert snap["changes"]["1d"] == 3 and snap["changes"]["1w"] is None and snap["trend"] is None
    assert (snap["advancers"], snap["decliners"]) == (1, 1)
    assert snap["sentiment"]["article_count"] == 3 and snap["sentiment"]["score"] == 0.5
    assert snap["sentiment"]["label"] == "positive"
    assert snap["stocks"][0]["sentiment_label"] is None  # only two articles


def test_stale_and_missing_stocks_are_left_out() -> None:
    stale = rows([100, 200], end=NOW - timedelta(days=30))
    snap = build_snapshot("x", "X", {"A": rows([100, 110]), "B": stale, "C": []}, {}, NOW)
    assert snap["changes"]["1d"] == 10 and snap["priced_count"] == 1 and snap["stock_count"] == 3
    assert snap["sentiment"]["score"] is None and snap["sentiment"]["label"] is None
    assert build_snapshot("x", "X", {"C": []}, {}, NOW)["as_of"] is None


async def test_refresh_stores_one_snapshot_per_sector(mongo_test_db) -> None:
    await get_prices_collection().insert_many([{"ticker": "SUNPHARMA.NS", **r} for r in rows([100, 105])])
    base = {"title": "t", "tickers": ["SUNPHARMA.NS"], "sentiment": {"score": 0.5, "label": "positive"}}
    await get_news_collection().insert_many(
        [
            {**base, "url": "new", "published_at": NOW},
            {**base, "url": "old", "published_at": NOW - timedelta(days=30)},
        ]
    )
    for _ in range(2):  # idempotent
        assert await refresh_sectors(NOW) == len(SECTORS)
    assert len(await sector_repository.list_snapshots()) == len(SECTORS)
    pharma = await sector_repository.get_snapshot("pharma")
    assert pharma["changes"]["1d"] == 5 and pharma["sentiment"]["article_count"] == 1


def test_routes(client, auth_headers) -> None:
    assert client.get("/api/v1/sectors").status_code == 401
    assert client.get("/api/v1/sectors", headers=auth_headers).json() == []
    assert client.get("/api/v1/sectors/nope", headers=auth_headers).status_code == 404
    client.portal.call(refresh_sectors)
    body = client.get("/api/v1/sectors", headers=auth_headers).json()
    assert len(body) == len(SECTORS)
    assert client.get("/api/v1/sectors/it", headers=auth_headers).json()["stock_count"] == 3
