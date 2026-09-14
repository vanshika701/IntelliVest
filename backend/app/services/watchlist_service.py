"""Service layer for the smart watchlist.

Enriches stored watchlist items with latest price data from the prices
collection — the repository stores notes/priority, this service merges
market data on read so the dashboard gets a single combined payload.
"""

import logging

from app.data.collections import get_prices_collection
from app.data.watchlist_repository import (
    add_watchlist_item,
    get_watchlist_for_user,
    remove_watchlist_item,
    update_watchlist_item,
)

logger = logging.getLogger(__name__)


async def _get_latest_prices(tickers: list[str]) -> dict[str, dict]:
    """Fetch the two most recent price records per ticker for change calculation."""
    if not tickers:
        return {}

    prices_col = get_prices_collection()
    pipeline = [
        {"$match": {"ticker": {"$in": tickers}}},
        {"$sort": {"date": -1}},
        {
            "$group": {
                "_id": "$ticker",
                "prices": {"$push": {"close": "$close", "date": "$date"}},
            }
        },
        # Only keep the 2 most recent to compute day-over-day change.
        {"$project": {"_id": 1, "prices": {"$slice": ["$prices", 2]}}},
    ]
    cursor = prices_col.aggregate(pipeline)
    results = await cursor.to_list(length=200)

    price_map: dict[str, dict] = {}
    for row in results:
        ticker = row["_id"]
        entries = row["prices"]
        latest = entries[0]["close"] if entries else None
        prev = entries[1]["close"] if len(entries) > 1 else None
        change_pct = None
        if latest is not None and prev is not None and prev != 0:
            change_pct = round(((latest - prev) / prev) * 100, 2)
        price_map[ticker] = {
            "latest_price": latest,
            "previous_close": prev,
            "change_pct": change_pct,
        }
    return price_map


async def add_to_watchlist(user_id: str, item: dict) -> str | None:
    """Add a ticker to the user's watchlist. Returns ID or None if duplicate."""
    return await add_watchlist_item(user_id, item)


async def get_enriched_watchlist(user_id: str) -> list[dict]:
    """Return the user's watchlist items enriched with latest price data."""
    items = await get_watchlist_for_user(user_id)
    if not items:
        return []

    tickers = [item["ticker"] for item in items]
    price_map = await _get_latest_prices(tickers)

    enriched = []
    for item in items:
        item["id"] = str(item.pop("_id"))
        ticker_prices = price_map.get(item["ticker"], {})
        item["latest_price"] = ticker_prices.get("latest_price")
        item["previous_close"] = ticker_prices.get("previous_close")
        item["change_pct"] = ticker_prices.get("change_pct")
        enriched.append(item)

    return enriched


async def update_item(user_id: str, item_id: str, updates: dict) -> bool:
    return await update_watchlist_item(user_id, item_id, updates)


async def remove_item(user_id: str, item_id: str) -> bool:
    return await remove_watchlist_item(user_id, item_id)
