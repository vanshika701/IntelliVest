"""Data-access layer for `stock_predictions`: one document per stock, as-of
date and horizon, written by the daily prediction job."""

from datetime import datetime

from pymongo import DESCENDING, ReplaceOne

from app.data.collections import get_stock_predictions_collection

KEY_FIELDS = ("ticker", "as_of", "horizon_days")


async def replace_predictions(docs: list[dict]) -> None:
    if not docs:
        return
    operations = [ReplaceOne({k: d[k] for k in KEY_FIELDS}, d, upsert=True) for d in docs]
    await get_stock_predictions_collection().bulk_write(operations, ordered=False)


async def get_latest_for_ticker(ticker: str) -> list[dict]:
    """Every horizon of the ticker's newest prediction day."""
    collection = get_stock_predictions_collection()
    newest = await collection.find_one(
        {"ticker": ticker}, {"as_of": 1}, sort=[("as_of", DESCENDING)]
    )
    if newest is None:
        return []
    cursor = collection.find({"ticker": ticker, "as_of": newest["as_of"]}, {"_id": 0}).sort(
        "horizon_days", 1
    )
    return await cursor.to_list(length=None)


async def get_latest_run() -> dict | None:
    """as_of and artifact hash of the newest stored prediction."""
    return await get_stock_predictions_collection().find_one(
        {},
        {"_id": 0, "as_of": 1, "artifact_hash": 1},
        sort=[("as_of", DESCENDING), ("created_at", DESCENDING)],
    )


async def latest_as_of() -> datetime | None:
    run = await get_latest_run()
    return run["as_of"] if run else None
