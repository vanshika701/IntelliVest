"""Integration test — proves upsert_prices is actually idempotent against
a real MongoDB instance, which is the core property Phase 1's ingestion
depends on (re-running a pull must not create duplicate rows).
"""

from datetime import UTC, datetime

from app.data.collections import get_prices_collection
from app.data.prices_repository import upsert_prices


async def test_upsert_prices_updates_in_place_instead_of_duplicating(mongo_test_db) -> None:
    record = {
        "ticker": "TEST.NS",
        "date": datetime(2026, 1, 1, tzinfo=UTC),
        "open": 100.0,
        "high": 101.0,
        "low": 99.0,
        "close": 100.5,
        "volume": 1000,
    }

    first_pass_count = await upsert_prices([record])
    assert first_pass_count == 1

    # Simulate re-running ingestion for the same day with a revised close
    # price (e.g. the source corrected an earlier value).
    updated_record = {**record, "close": 102.0}
    second_pass_count = await upsert_prices([updated_record])
    assert second_pass_count == 1

    stored = await get_prices_collection().find({"ticker": "TEST.NS"}).to_list(length=None)
    assert len(stored) == 1
    assert stored[0]["close"] == 102.0
