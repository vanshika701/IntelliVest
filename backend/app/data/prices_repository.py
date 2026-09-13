"""Data-access layer for the `prices` collection — the only module that
knows how a price document actually gets written to Mongo.
"""

from datetime import UTC, datetime

from pymongo import UpdateOne

from app.data.collections import get_prices_collection


async def upsert_prices(records: list[dict]) -> int:
    """Upsert OHLCV records, keyed on (ticker, date).

    Using bulk_write with upsert=True is what makes ingestion idempotent:
    re-running a pull for a date that's already stored updates that one
    document in place instead of inserting a duplicate — relies entirely
    on the uniq_ticker_date index already existing (see data/indexes.py).
    """
    if not records:
        return 0

    now = datetime.now(UTC)
    operations = [
        UpdateOne(
            {"ticker": record["ticker"], "date": record["date"]},
            {"$set": {**record, "ingested_at": now}},
            upsert=True,
        )
        for record in records
    ]

    result = await get_prices_collection().bulk_write(operations, ordered=False)
    return result.upserted_count + result.modified_count
