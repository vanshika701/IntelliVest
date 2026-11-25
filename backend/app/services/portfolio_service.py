"""What the user's (demo) investments are worth now, per instrument.

Completed one-time orders count at their order price. An active SIP counts each
instalment that has come due, bought at the first price on or after its date;
no real instalments run, so these are worked out from price history.
"""

import asyncio
import logging
from datetime import date, datetime

from app.data.investment_repository import list_held_investments
from app.services.instrument_service import DataProviderError, InstrumentNotFound, get_prices
from app.services.investment_service import IST, installment_dates

logger = logging.getLogger(__name__)

Series = list[tuple[date, float]]


def invested_and_units(investment: dict, series: Series, today: date) -> tuple[float, float]:
    if investment["kind"] == "one_time":
        # Not the stored units: those are rounded, so a new order would show a loss of paise.
        price = investment["price_at_order"]
        return investment["amount"], investment["amount"] / price if price else 0.0
    invested = units = 0.0
    for due in installment_dates(investment, today):
        price = next((value for day, value in series if day >= due), None)
        if price:  # not priced yet: counts from the next price
            invested += investment["amount"]
            units += investment["amount"] / price
    return invested, units


def build_holding(investments: list[dict], series: Series, price: float | None, today: date) -> dict | None:
    """One instrument's position, or None if nothing has been bought yet."""
    lots = [invested_and_units(i, series, today) for i in investments]
    invested = round(sum(amount for amount, _ in lots), 2)
    if invested <= 0:
        return None
    # An order placed without a price has unknown units, so no honest value.
    known = price is not None and all(units > 0 for amount, units in lots if amount > 0)
    value = round(sum(units for _, units in lots) * price, 2) if known else None
    first = investments[0]
    return {
        "instrument_id": first["instrument_id"],
        "instrument_name": first["instrument_name"],
        "instrument_type": first["instrument_type"],
        "invested": invested,
        "current_value": value,
        **_gain(invested, value),
    }


def _gain(invested: float, value: float | None) -> dict:
    if value is None:
        return {"gain": None, "gain_pct": None}
    gain = round(value - invested, 2)
    return {"gain": gain, "gain_pct": round(gain / invested * 100, 2) if invested else None}


async def _prices(instrument_id: str) -> tuple[Series, float | None]:
    try:
        return await get_prices(instrument_id)
    except (DataProviderError, InstrumentNotFound) as exc:
        logger.warning("No price for holding %s: %s", instrument_id, exc)
        return [], None


async def get_portfolio(user_id: str, today: date | None = None) -> dict:
    today = today or datetime.now(IST).date()
    groups: dict[str, list[dict]] = {}
    for investment in await list_held_investments(user_id):
        groups.setdefault(investment["instrument_id"], []).append(investment)
    prices = await asyncio.gather(*(_prices(i) for i in groups))
    built = [build_holding(g, *p, today) for g, p in zip(groups.values(), prices, strict=True)]
    holdings = sorted(
        (h for h in built if h), key=lambda h: h["current_value"] or h["invested"], reverse=True
    )
    # Totals compare like with like: only holdings that could be valued.
    valued = [h for h in holdings if h["current_value"] is not None]
    invested = round(sum(h["invested"] for h in valued), 2)
    value = round(sum(h["current_value"] for h in valued), 2)
    return {
        "invested": invested,
        "current_value": value,
        **_gain(invested, value),
        "unvalued_count": len(holdings) - len(valued),
        "holdings": holdings,
    }
