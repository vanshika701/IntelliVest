"""Horizons: what the user picks (days, months, years) vs what is stored.

The daily job stores a prediction for each horizon in HORIZON_GRID
(trading days). A request for any other horizon reads the two stored
horizons either side and interpolates between them on a log scale, so
requests never run the model.
"""

import math
from dataclasses import dataclass
from datetime import date
from typing import Literal

from dateutil.relativedelta import relativedelta

Unit = Literal["days", "months", "years"]

HORIZON_GRID: tuple[int, ...] = (1, 2, 3, 5, 7, 10, 15, 21, 31, 42, 63, 94, 126, 189, 252, 378, 504)
MAX_TRADING_DAYS = HORIZON_GRID[-1]

TRADING_DAYS_PER_YEAR = 252
TRADING_DAYS_PER_MONTH = 21
UNIT_LIMITS: dict[str, int] = {"days": 730, "months": 24, "years": 2}

# Horizon groups for reporting test results (upper bound, inclusive).
HORIZON_GROUPS: tuple[tuple[str, int], ...] = (
    ("Up to 1 week", 5),
    ("1 week to 1 month", 21),
    ("1 to 6 months", 126),
    ("6 months to 2 years", 504),
)


def to_trading_days(amount: int, unit: Unit) -> int:
    if not 1 <= amount <= UNIT_LIMITS[unit]:
        raise ValueError(f"Choose 1 to {UNIT_LIMITS[unit]} {unit}")
    if unit == "days":
        days = round(amount * TRADING_DAYS_PER_YEAR / 365)
    elif unit == "months":
        days = amount * TRADING_DAYS_PER_MONTH
    else:
        days = amount * TRADING_DAYS_PER_YEAR
    return min(max(days, 1), MAX_TRADING_DAYS)


def target_date(as_of: date, amount: int, unit: Unit) -> date:
    if unit == "days":
        return as_of + relativedelta(days=amount)
    if unit == "months":
        return as_of + relativedelta(months=amount)
    return as_of + relativedelta(years=amount)


def horizon_group(trading_days: int) -> str:
    for label, upper in HORIZON_GROUPS:
        if trading_days <= upper:
            return label
    return HORIZON_GROUPS[-1][0]


@dataclass(frozen=True)
class Forecast:
    """Excess log returns over the Nifty 50 for the horizon, at the 10th,
    50th and 90th percentile, and the chance of beating it."""

    chance_beat: float
    low: float
    mid: float
    high: float


def interpolate(stored: dict[int, Forecast], trading_days: int) -> Forecast:
    if trading_days in stored:
        return stored[trading_days]
    below = max((h for h in stored if h < trading_days), default=None)
    above = min((h for h in stored if h > trading_days), default=None)
    if below is None or above is None:
        nearest = above if below is None else below
        if nearest is None:
            raise KeyError("No stored horizons")
        return stored[nearest]
    w = (math.log(trading_days) - math.log(below)) / (math.log(above) - math.log(below))
    a, b = stored[below], stored[above]
    return Forecast(
        *(
            x + w * (y - x)
            for x, y in zip(
                (a.chance_beat, a.low, a.mid, a.high),
                (b.chance_beat, b.low, b.mid, b.high),
                strict=True,
            )
        )
    )
