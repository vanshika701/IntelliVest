"""Data access for Phase 7 `market_stats`: one document per price date.

Keyed on `as_of` (the last price date used), so re-running the job on the
same prices replaces that day's document instead of adding a duplicate,
while earlier days stay available to explain past recommendations.
"""

from pymongo import ReplaceOne

from app.data.collections import get_market_stats_collection


async def save_stats(stats: dict) -> None:
    await get_market_stats_collection().bulk_write(
        [ReplaceOne({"as_of": stats["as_of"]}, stats, upsert=True)]
    )


async def get_latest_stats() -> dict | None:
    return await get_market_stats_collection().find_one({}, {"_id": 0}, sort=[("as_of", -1)])
