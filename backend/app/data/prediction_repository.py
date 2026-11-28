"""Data-access layer for `stock_predictions`: one document per stock, as-of
date, horizon and model, written by the daily prediction job.

`model` is the prediction model's key (prediction_service.PREDICTION_MODELS).
Rows stored before models could be chosen have no `model`; they came from
LightGBM and `migrate_legacy_rows` labels them "lgbm".
"""

from datetime import datetime

from pymongo import DESCENDING, ReplaceOne

from app.core.config import settings
from app.data.collections import get_stock_predictions_collection

KEY_FIELDS = ("ticker", "as_of", "horizon_days", "model")
LEGACY_MODEL = "lgbm"


def _model(model: str | None) -> str:
    return model or settings.prediction_model


async def replace_predictions(docs: list[dict]) -> None:
    if not docs:
        return
    operations = [ReplaceOne({k: d[k] for k in KEY_FIELDS}, d, upsert=True) for d in docs]
    await get_stock_predictions_collection().bulk_write(operations, ordered=False)


async def get_latest_for_ticker(ticker: str, model: str | None = None) -> list[dict]:
    """Every horizon of the ticker's newest prediction day from `model`
    (default: the configured default model)."""
    collection = get_stock_predictions_collection()
    query = {"ticker": ticker, "model": _model(model)}
    newest = await collection.find_one(query, {"as_of": 1}, sort=[("as_of", DESCENDING)])
    if newest is None:
        return []
    cursor = collection.find({**query, "as_of": newest["as_of"]}, {"_id": 0}).sort("horizon_days", 1)
    return await cursor.to_list(length=None)


async def get_latest_run(model: str | None = None) -> dict | None:
    """as_of and artifact hash of the newest scheduled (tracked-stock) run
    of `model`. On-demand predictions for untracked stocks are left out."""
    return await get_stock_predictions_collection().find_one(
        {"tracked": {"$ne": False}, "model": _model(model)},
        {"_id": 0, "as_of": 1, "artifact_hash": 1},
        sort=[("as_of", DESCENDING), ("created_at", DESCENDING)],
    )


async def latest_as_of() -> datetime | None:
    run = await get_latest_run()
    return run["as_of"] if run else None


async def migrate_legacy_rows() -> int:
    """Label rows from before model choice as LightGBM's. Returns how many."""
    result = await get_stock_predictions_collection().update_many(
        {"model": {"$exists": False}}, {"$set": {"model": LEGACY_MODEL}}
    )
    return result.modified_count
