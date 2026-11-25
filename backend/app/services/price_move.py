"""A one-line, factual price move from our own data, shown above the news
summary because headlines often don't say which way the price went."""

import logging
from datetime import date, timedelta

from app.services.instrument_service import DataProviderError, get_daily_history, get_instrument

logger = logging.getLogger(__name__)

# Bigger moves are almost always a unit/stock split in the data, not a real move.
MAX_PLAUSIBLE_PCT = 50.0
FLAT_PCT = 0.05
# The comparison price must be at most this much older than asked for.
MAX_GAP_DAYS = 7


def pct_since(points: list[tuple[date, float]], price: float, as_of: date, days: int) -> float | None:
    """% change from the last price on or before `as_of - days`."""
    target = as_of - timedelta(days=days)
    earlier = [(d, v) for d, v in points if d <= target]
    if not earlier or earlier[-1][1] <= 0 or (target - earlier[-1][0]).days > MAX_GAP_DAYS:
        return None
    return _plausible((price / earlier[-1][1] - 1) * 100)


def _plausible(pct: float | None) -> float | None:
    return round(pct, 2) if pct is not None and abs(pct) <= MAX_PLAUSIBLE_PCT else None


def describe(pct: float) -> str:
    return "flat" if abs(pct) < FLAT_PCT else f"{'up' if pct > 0 else 'down'} {abs(pct):.1f}%"


def build_price_move(
    name: str, points: list[tuple[date, float]], price: float | None, as_of: date | None, day_pct: float | None
) -> dict | None:
    if price is None or as_of is None:
        return None
    moves = {
        "day_pct": _plausible(day_pct),
        "week_pct": pct_since(points, price, as_of, 7),
        "month_pct": pct_since(points, price, as_of, 30),
    }
    labels = {"day_pct": "on the day", "week_pct": "over a week", "month_pct": "over a month"}
    parts = [f"{describe(v)} {labels[k]}" for k, v in moves.items() if v is not None]
    if not parts:
        return None
    sentence = parts[0] if len(parts) == 1 else f"{', '.join(parts[:-1])} and {parts[-1]}"
    return {"as_of": as_of, **moves, "text": f"{name.split(' - ')[0]}: {sentence} (as of {as_of.day} {as_of:%b %Y})."}


async def get_price_move(instrument_id: str) -> dict | None:
    """None if prices are unavailable; the news summary doesn't depend on it."""
    try:
        instrument = await get_instrument(instrument_id)
        history = await get_daily_history(instrument_id)
    except DataProviderError as exc:
        logger.warning("Price move unavailable for %s: %s", instrument_id, exc)
        return None
    points = [(date.fromisoformat(p["t"]), p["v"]) for p in history["points"]]
    return build_price_move(
        instrument["name"], points, instrument["price"], instrument["price_date"], instrument["day_change_pct"]
    )
