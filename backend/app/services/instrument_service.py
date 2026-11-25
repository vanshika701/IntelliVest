"""Service layer for instruments: stocks (the tracked NSE universe, prices
from the `prices` collection + yfinance intraday) and mutual funds / ETFs
(mfapi.in), behind one id scheme:

    stock-<TICKER>   e.g. stock-TCS.NS
    mf-<SCHEME_CODE> e.g. mf-111954   (MF or ETF, decided from the name)
"""

import asyncio
import logging
import re
from datetime import UTC, date, datetime

import yfinance as yf

from app.core.cache import MISSING, TTLCache
from app.core.constants import STOCK_UNIVERSE, TICKER_TO_COMPANY_NAME
from app.data.prices_repository import get_close_series
from app.services import fund_meta_provider, mfapi_client

logger = logging.getLogger(__name__)

_intraday_cache = TTLCache(ttl_seconds=5 * 60, max_items=64)


class InstrumentNotFound(Exception):
    pass


class DataProviderError(Exception):
    """An upstream market-data provider failed or timed out."""


def parse_instrument_id(instrument_id: str) -> tuple[str, str]:
    kind, _, ref = instrument_id.partition("-")
    if kind == "stock" and ref in STOCK_UNIVERSE:
        return "stock", ref
    if kind == "mf" and ref.isdigit():
        return "mf", ref
    raise InstrumentNotFound(instrument_id)


def classify_scheme(name: str) -> str:
    upper = name.upper()
    is_fof = "FUND OF FUND" in upper or re.search(r"\bFOF\b", upper) is not None
    is_etf = re.search(r"\bETF\b", upper) is not None or "EXCHANGE TRADED" in upper
    return "ETF" if is_etf and not is_fof else "MF"


def _variant_rank(name: str) -> int:
    """Prefer the variant most investors want: Direct, Growth; demote IDCW/dividend."""
    upper = name.upper()
    rank = 0
    rank += 2 if "DIRECT" in upper else 0
    rank += 1 if "GROWTH" in upper else 0
    rank -= 2 if ("IDCW" in upper or "DIVIDEND" in upper) else 0
    return -rank


def _search_stocks(query: str) -> list[dict]:
    q = query.strip().lower()
    results = []
    for ticker in STOCK_UNIVERSE:
        name = TICKER_TO_COMPANY_NAME.get(ticker, ticker)
        if q in name.lower() or q in ticker.lower().removesuffix(".ns"):
            results.append(
                {"id": f"stock-{ticker}", "name": name, "type": "STOCK", "symbol": ticker, "subtitle": f"NSE · {ticker}"}
            )
    return results


async def search_instruments(query: str, limit: int = 15) -> dict:
    """Stocks first, then funds. A fund-provider outage still returns the
    stock matches, with `partial` set so the UI can say results may be
    incomplete."""
    stocks = _search_stocks(query)
    partial = False
    try:
        schemes = await mfapi_client.search_schemes(query)
    except mfapi_client.MfApiError:
        schemes, partial = [], True

    # One entry per fund: plan/option variants ("SBI Gold Fund - Direct Plan
    # - Growth" vs "- Regular Plan - IDCW") share the part before " - ".
    best_by_fund: dict[str, dict] = {}
    for scheme in sorted(schemes, key=lambda s: _variant_rank(s["scheme_name"])):
        best_by_fund.setdefault(scheme["scheme_name"].split(" - ")[0].strip().lower(), scheme)

    q = query.strip().lower()
    schemes = sorted(
        best_by_fund.values(),
        key=lambda s: (not s["scheme_name"].lower().startswith(q), len(s["scheme_name"])),
    )
    funds = [
        {
            "id": f"mf-{s['scheme_code']}",
            "name": s["scheme_name"],
            "type": classify_scheme(s["scheme_name"]),
            "symbol": str(s["scheme_code"]),
            "subtitle": "Mutual fund scheme",
        }
        for s in schemes
    ]
    return {"query": query, "results": (stocks + funds)[:limit], "partial": partial}


async def _daily_series(kind: str, ref: str) -> tuple[list[tuple[date, float]], dict]:
    if kind == "stock":
        rows = await get_close_series(ref)
        return [(r["date"].date(), float(r["close"])) for r in rows], {}
    try:
        scheme = await mfapi_client.get_scheme(int(ref))
    except mfapi_client.MfApiError as exc:
        raise DataProviderError(str(exc)) from exc
    if scheme is None:
        raise InstrumentNotFound(ref)
    return scheme["navs"], scheme["meta"]


async def get_instrument(instrument_id: str) -> dict:
    kind, ref = parse_instrument_id(instrument_id)
    series, meta = await _daily_series(kind, ref)

    if kind == "stock":
        name, instrument_type = TICKER_TO_COMPANY_NAME.get(ref, ref), "STOCK"
        subtitle, category = f"NSE · {ref}", "Equity"
    else:
        name = meta["scheme_name"]
        instrument_type = classify_scheme(name)
        subtitle, category = meta.get("fund_house"), meta.get("scheme_category")

    price = series[-1][1] if series else None
    previous = series[-2][1] if len(series) >= 2 else None
    day_change = round(price - previous, 4) if price is not None and previous else None
    day_change_pct = round(day_change / previous * 100, 4) if day_change is not None else None

    return {
        "id": instrument_id,
        "name": name,
        "type": instrument_type,
        "symbol": ref,
        "subtitle": subtitle,
        "category": category,
        "currency": "INR",
        "price": price,
        "price_date": series[-1][0] if series else None,
        "previous_price": previous,
        "day_change": day_change,
        "day_change_pct": day_change_pct,
        "supports_intraday": kind == "stock",
        "stats": await fund_meta_provider.get_meta(
            instrument_type,
            price,
            ticker=ref if kind == "stock" else None,
            isin=meta.get("isin_growth") or meta.get("isin_div_reinvestment"),
        ),
    }


async def get_daily_history(instrument_id: str) -> dict:
    kind, ref = parse_instrument_id(instrument_id)
    series, _ = await _daily_series(kind, ref)
    return {"interval": "1d", "points": [{"t": day.isoformat(), "v": round(value, 4)} for day, value in series]}


def _fetch_intraday(ticker: str) -> list[dict]:
    history = yf.Ticker(ticker).history(period="1d", interval="5m", timeout=10)
    return [
        {"t": ts.to_pydatetime().astimezone(UTC).isoformat(), "v": round(float(close), 4)}
        for ts, close in history["Close"].dropna().items()
    ]


async def get_intraday_history(instrument_id: str) -> dict:
    """5-minute bars for the last trading session (stocks only — mutual
    funds only publish one NAV a day)."""
    kind, ref = parse_instrument_id(instrument_id)
    if kind != "stock":
        return {"interval": "5m", "points": []}

    cached = _intraday_cache.get(ref)
    if cached is not MISSING:
        return cached
    try:
        points = await asyncio.wait_for(asyncio.to_thread(_fetch_intraday, ref), timeout=20)
    except Exception as exc:
        logger.warning("Intraday fetch failed for %s: %s", ref, exc)
        raise DataProviderError("Intraday prices are unavailable") from exc

    result = {"interval": "5m", "points": points, "fetched_at": datetime.now(UTC).isoformat()}
    _intraday_cache.set(ref, result)
    return result
