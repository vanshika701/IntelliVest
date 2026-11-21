"""Integration test — verifies the collections actually have the indexes
Phase 1 depends on, and that the unique index on (ticker, date) really
enforces idempotent ingestion (a duplicate insert gets rejected, which is
what lets the ingestion job safely re-run without creating duplicate rows).
"""

from datetime import UTC, datetime

import pytest
from pymongo.errors import DuplicateKeyError

from app.data.collections import (
    get_alerts_collection,
    get_expenses_collection,
    get_news_collection,
    get_prices_collection,
    get_reddit_collection,
    get_users_collection,
    get_watchlist_collection,
)


async def test_all_collections_have_expected_index_names(mongo_test_db) -> None:
    prices_indexes = await get_prices_collection().index_information()
    news_indexes = await get_news_collection().index_information()
    reddit_indexes = await get_reddit_collection().index_information()
    users_indexes = await get_users_collection().index_information()
    expenses_indexes = await get_expenses_collection().index_information()
    watchlist_indexes = await get_watchlist_collection().index_information()
    alerts_indexes = await get_alerts_collection().index_information()

    assert "uniq_ticker_date" in prices_indexes
    assert "uniq_url" in news_indexes
    assert "tickers_published_at" in news_indexes
    assert "uniq_post_id" in reddit_indexes
    assert "subreddit_created_utc" in reddit_indexes
    assert "uniq_email" in users_indexes
    assert "user_expenses_by_date" in expenses_indexes
    assert "uniq_user_ticker" in watchlist_indexes
    assert "user_active_alerts" in alerts_indexes
    assert "ticker_active_alerts" in alerts_indexes


async def test_duplicate_ticker_date_insert_is_rejected(mongo_test_db) -> None:
    prices = get_prices_collection()
    doc = {
        "ticker": "TEST.NS",
        "date": datetime(2026, 1, 1, tzinfo=UTC),
        "open": 100.0,
        "high": 101.0,
        "low": 99.0,
        "close": 100.5,
        "volume": 1000,
    }

    await prices.insert_one(doc)

    with pytest.raises(DuplicateKeyError):
        await prices.insert_one(doc)
