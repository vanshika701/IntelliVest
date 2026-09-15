"""Service layer for price proximity alerts.

Owns the rule-evaluation logic: given a current price and an alert's
condition/target, decide whether it triggers.  The background check job
calls evaluate_all_alerts() on a schedule; the route layer calls the
CRUD helpers.
"""

import logging

from app.data.alert_repository import (
    create_alert,
    delete_alert,
    get_alerts_for_user,
    get_all_active_alerts,
    mark_alert_triggered,
    toggle_alert_active,
)
from app.data.collections import get_prices_collection

logger = logging.getLogger(__name__)


def _check_trigger(condition: str, current_price: float, target: float, threshold_pct: float) -> bool:
    """Pure rule evaluation — no I/O, easy to unit test."""
    if condition == "above":
        return current_price >= target
    if condition == "below":
        return current_price <= target
    if condition == "within_pct":
        if target == 0:
            return False
        pct_diff = abs((current_price - target) / target) * 100
        return pct_diff <= threshold_pct
    return False


async def add_alert(user_id: str, data: dict) -> str:
    return await create_alert(user_id, data)


async def list_alerts(user_id: str) -> list[dict]:
    items = await get_alerts_for_user(user_id)
    if not items:
        return []

    # Enrich with each ticker's latest close so the UI can show "target
    # $150, currently $142" instead of just the bare rule.
    tickers = {item["ticker"] for item in items}
    price_cache = {ticker: await _get_latest_close(ticker) for ticker in tickers}

    for item in items:
        item["id"] = str(item.pop("_id"))
        item["latest_price"] = price_cache.get(item["ticker"])
    return items


async def toggle(user_id: str, alert_id: str, is_active: bool) -> bool:
    return await toggle_alert_active(user_id, alert_id, is_active)


async def remove_alert(user_id: str, alert_id: str) -> bool:
    return await delete_alert(user_id, alert_id)


async def _get_latest_close(ticker: str) -> float | None:
    """Fetch the most recent closing price for a ticker."""
    prices_col = get_prices_collection()
    doc = await prices_col.find_one(
        {"ticker": ticker},
        sort=[("date", -1)],
        projection={"close": 1},
    )
    return doc["close"] if doc else None


async def evaluate_all_alerts() -> int:
    """Check every active alert against its ticker's latest price.

    Called by the background scheduler.  Returns the number of newly
    triggered alerts.
    """
    alerts = await get_all_active_alerts()
    if not alerts:
        return 0

    # Batch-fetch latest prices for all distinct tickers
    tickers = list({a["ticker"] for a in alerts})
    price_cache: dict[str, float | None] = {}
    for ticker in tickers:
        price_cache[ticker] = await _get_latest_close(ticker)

    triggered_count = 0
    for alert in alerts:
        current_price = price_cache.get(alert["ticker"])
        if current_price is None:
            continue

        if _check_trigger(
            alert["condition"],
            current_price,
            alert["target_price"],
            alert.get("threshold_pct", 5.0),
        ):
            await mark_alert_triggered(str(alert["_id"]))
            triggered_count += 1
            logger.info(
                "Alert triggered: user=%s ticker=%s condition=%s target=%.2f current=%.2f",
                alert["user_id"],
                alert["ticker"],
                alert["condition"],
                alert["target_price"],
                current_price,
            )

    logger.info("Alert evaluation complete: %d of %d alerts triggered", triggered_count, len(alerts))
    return triggered_count
