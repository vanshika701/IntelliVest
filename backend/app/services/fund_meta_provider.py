"""Instrument metadata beyond prices: rating, size and minimum amounts.

Live from Yahoo Finance (the source the app already uses for stock prices):
- funds: Morningstar overall star rating, looked up by the scheme's ISIN;
- stocks: market cap and the analysts' consensus.

Fund size comes from AMFI, by scheme code (Yahoo's is missing or implausible
for most Indian schemes). Fund minimums are still placeholders. Each lookup has a timeout, is cached, and returns no
values on failure, so it can never break the instrument page.
"""

import asyncio
import logging
import math

import yfinance as yf

from app.core.cache import MISSING, TTLCache
from app.services import fund_aum_provider

logger = logging.getLogger(__name__)

# TODO(mock): industry-typical defaults, flagged via `placeholder_fields`.
PLACEHOLDER_MF_MIN_SIP = 500
PLACEHOLDER_MF_MIN_INVESTMENT = 1000

LOOKUP_TIMEOUT_SECONDS = 6
_cache = TTLCache(ttl_seconds=12 * 60 * 60, max_items=512)
# Failures are retried sooner.
_failures = TTLCache(ttl_seconds=5 * 60, max_items=512)


def stars(value) -> float | None:
    """Morningstar stars 1-5. Yahoo sends 0 for an unrated fund."""
    return float(value) if isinstance(value, (int, float)) and 1 <= value <= 5 else None


def _fetch_fund(isin: str) -> dict:
    quotes = yf.Search(isin, max_results=1, news_count=0, timeout=LOOKUP_TIMEOUT_SECONDS).quotes
    if not quotes or quotes[0].get("quoteType") != "MUTUALFUND":
        return {}
    rating = stars(yf.Ticker(quotes[0]["symbol"]).info.get("morningStarOverallRating"))
    return {"rating": rating, "rating_source": "Morningstar via Yahoo Finance"} if rating else {}


def _fetch_stock(ticker: str) -> dict:
    info = yf.Ticker(ticker).info
    out: dict = {}
    if info.get("marketCap"):
        out["market_cap_crore"] = round(info["marketCap"] / 1e7, 2)
    key = info.get("recommendationKey")
    if key and key != "none" and info.get("numberOfAnalystOpinions"):
        out["analyst_rating"] = key.replace("_", " ").title()
        out["analyst_count"] = info["numberOfAnalystOpinions"]
        out["rating_source"] = "Analyst consensus via Yahoo Finance"
    return out


async def _live(key: str, fetch, arg: str) -> dict:
    for cache in (_cache, _failures):
        cached = cache.get(key)
        if cached is not MISSING:
            return cached
    try:
        result = await asyncio.wait_for(asyncio.to_thread(fetch, arg), timeout=LOOKUP_TIMEOUT_SECONDS)
    except Exception as exc:  # noqa: BLE001 - optional data must never break the page
        logger.warning("Live metadata lookup failed for %s: %s", key, exc)
        _failures.set(key, {})
        return {}
    _cache.set(key, result)
    return result


async def get_meta(
    instrument_type: str,
    price: float | None,
    ticker: str | None = None,
    isin: str | None = None,
    scheme_code: int | None = None,
) -> dict:
    one_unit = math.ceil(price) if price else None
    meta = {
        "rating": None,
        "rating_source": None,
        "analyst_rating": None,
        "analyst_count": None,
        "market_cap_crore": None,
        "aum_crore": None,
        "aum_period": None,
        # ETFs: one unit at NAV, approximate since they trade at exchange prices.
        "min_sip": one_unit,
        "min_investment": one_unit,
        "placeholder_fields": ["min_sip", "min_investment"],
        "source": "placeholder",
    }
    if instrument_type == "STOCK":
        # Real, derived value: you can't buy less than one share.
        meta |= {"placeholder_fields": [], "source": "derived"}
        if ticker:
            meta |= await _live(f"stock:{ticker}", _fetch_stock, ticker)
        return meta
    if instrument_type == "MF":
        meta |= {"min_sip": PLACEHOLDER_MF_MIN_SIP, "min_investment": PLACEHOLDER_MF_MIN_INVESTMENT}
    if isin:
        meta |= await _live(f"fund:{isin}", _fetch_fund, isin)
    if scheme_code is not None:
        meta |= await fund_aum_provider.get_aum(scheme_code)
    return meta
