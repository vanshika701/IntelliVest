"""Data-access layer for the `prices` collection — the only module that
knows how a price document actually gets written to Mongo.
"""

from datetime import UTC, datetime

from pymongo import DESCENDING, UpdateOne

from app.data.collections import get_prices_collection

# `date` is the exchange's own trading day (stored as midnight UTC).
DATE_BASIS = "exchange"


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
            {"$set": {**record, "date_basis": DATE_BASIS, "ingested_at": now}},
            upsert=True,
        )
        for record in records
    ]

    result = await get_prices_collection().bulk_write(operations, ordered=False)
    return result.upserted_count + result.modified_count


async def get_close_series(ticker: str) -> list[dict]:
    """Every stored daily close for `ticker`, oldest first. Served by the
    (ticker, date) unique index."""
    cursor = get_prices_collection().find(
        {"ticker": ticker}, {"_id": 0, "date": 1, "close": 1}
    ).sort("date", 1)
    return await cursor.to_list(length=None)


async def get_rows_without_date_basis() -> list[dict]:
    cursor = get_prices_collection().find(
        {"date_basis": {"$exists": False}}, {"ticker": 1, "date": 1}
    ).sort("date", DESCENDING)
    return await cursor.to_list(length=None)


async def replace_price_date(row: dict, new_date: datetime) -> None:
    """Move one row to `new_date`. A row already there is newer data, so it wins."""
    prices = get_prices_collection()
    if await prices.find_one({"ticker": row["ticker"], "date": new_date}, {"_id": 1}):
        await prices.delete_one({"_id": row["_id"]})
        return
    await prices.update_one(
        {"_id": row["_id"]}, {"$set": {"date": new_date, "date_basis": DATE_BASIS}}
    )


async def get_oldest_latest_date(tickers: list[str]) -> datetime | None:
    """The newest stored date of whichever ticker is furthest behind; None if
    any ticker has no prices."""
    cursor = get_prices_collection().aggregate(
        [
            {"$match": {"ticker": {"$in": tickers}}},
            {"$group": {"_id": "$ticker", "latest": {"$max": "$date"}}},
        ]
    )
    latest = [row["latest"] async for row in cursor]
    return min(latest) if len(latest) == len(tickers) else None
