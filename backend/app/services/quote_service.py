"""Latest stock quotes from Yahoo Finance, which reports NSE data as about 15
minutes delayed. One batched request covers the whole universe and is cached
for a minute. Failures return {}, and callers fall back to stored closes.
"""

import asyncio
import logging
from datetime import datetime, time
from zoneinfo import ZoneInfo

import yfinance as yf

from app.core.cache import MISSING, TTLCache
from app.core.constants import STOCK_UNIVERSE

logger = logging.getLogger(__name__)

IST = ZoneInfo("Asia/Kolkata")
MARKET_OPEN, MARKET_CLOSE = time(9, 15), time(15, 30)
DELAY_MINUTES = 15
TIMEOUT_SECONDS = 10

_cache = TTLCache(ttl_seconds=60, max_items=1)
_lock = asyncio.Lock()  # yf.download uses shared module state


def _closes(period: str, interval: str) -> dict[str, list[tuple[datetime, float]]]:
    frame = yf.download(
        STOCK_UNIVERSE,
        period=period,
        interval=interval,
        group_by="ticker",
        progress=False,
        timeout=TIMEOUT_SECONDS,
    )
    out = {}
    for ticker in STOCK_UNIVERSE:
        if ticker in frame.columns.get_level_values(0):
            closes = frame[ticker]["Close"].dropna()
            out[ticker] = [(i.to_pydatetime(), float(v)) for i, v in closes.items()]
    return out


def _download() -> dict[str, dict]:
    """ticker -> {"intraday": [(time, price)], "daily": [(day, close)]}. Yahoo's
    newest daily row can be blank for hours, so it only supplies earlier closes."""
    intraday, daily = _closes("5d", "5m"), _closes("5d", "1d")
    return {t: {"intraday": bars, "daily": daily.get(t, [])} for t, bars in intraday.items()}


def build_quote(bars: dict, now: datetime) -> dict | None:
    if not bars["intraday"]:
        return None
    last, price = bars["intraday"][-1]
    last = last.astimezone(IST)
    day = last.date()
    earlier = [v for t, v in bars["daily"] if t.date() < day] or [
        v for t, v in bars["intraday"] if t.astimezone(IST).date() < day
    ]
    previous = earlier[-1] if earlier else None
    local = now.astimezone(IST)
    return {
        "price": round(price, 4),
        "previous_close": previous,
        "change_pct": round((price / previous - 1) * 100, 2) if previous else None,
        "date": day,
        "market_open": day == local.date() and MARKET_OPEN <= local.time() <= MARKET_CLOSE,
        "fetched_at": now,
    }


async def get_quotes() -> dict[str, dict]:
    async with _lock:
        cached = _cache.get("quotes")
        if cached is not MISSING:
            return cached
        try:
            bars = await asyncio.wait_for(asyncio.to_thread(_download), timeout=2 * TIMEOUT_SECONDS)
        except Exception as exc:  # noqa: BLE001 - callers fall back to stored closes
            logger.warning("Live quotes unavailable: %s", exc)
            bars = {}
        now = datetime.now(IST)
        quotes = {t: q for t, b in bars.items() if (q := build_quote(b, now))}
        _cache.set("quotes", quotes)
        return quotes
