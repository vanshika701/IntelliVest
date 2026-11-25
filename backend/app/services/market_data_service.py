"""Service layer for market data ingestion.

This is the seam between the external API (yfinance, called here) and
storage (app/data/prices_repository.py, which owns the actual Mongo
write) — cleaning/validation logic belongs in this middle layer, not in
either of those.
"""

import asyncio
import logging
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import pandas as pd
import yfinance as yf

from app.core.retry import with_retry
from app.data.prices_repository import get_oldest_latest_date, upsert_prices
from app.services.ingestion_types import IngestResult

logger = logging.getLogger(__name__)

IST = ZoneInfo("Asia/Kolkata")
# NSE closes at 15:30 IST; by now the day's bar is final.
DAY_FINAL_AT = time(16, 0)
CATCH_UP_RETRY = timedelta(hours=3)
_last_catch_up: datetime | None = None


@with_retry
async def _fetch_history(ticker: str, period: str) -> pd.DataFrame:
    # yfinance's .history() is a blocking network call; run it on a
    # worker thread so it doesn't freeze the event loop this coroutine is
    # running on (this matters once ingestion runs inside the same
    # process as the API, driven by the scheduler below).
    return await asyncio.to_thread(yf.Ticker(ticker).history, period=period, interval="1d")


def last_final_weekday(now: datetime) -> date:
    """The latest weekday whose trading has finished (holidays not known)."""
    local = now.astimezone(IST)
    day = local.date() if local.time() >= DAY_FINAL_AT else local.date() - timedelta(days=1)
    while day.weekday() >= 5:
        day -= timedelta(days=1)
    return day


def clean_history(ticker: str, history: pd.DataFrame, now: datetime | None = None) -> list[dict]:
    """Turn yfinance's raw DataFrame into clean, storage-ready records.
    Today's bar is left out until the market has closed."""
    now = now or datetime.now(UTC)
    # A row missing any OHLCV field isn't usable — better to drop it than
    # let a null silently corrupt an average or a backtest later.
    history = history.dropna(subset=["Open", "High", "Low", "Close", "Volume"])

    records = []
    for index, row in history.iterrows():
        # yfinance's index is midnight in the exchange's timezone. Keep that
        # calendar day and label it UTC. Converting the instant to UTC would
        # move every IST date back by one.
        local_now = now.astimezone(index.tzinfo)
        if index.date() == local_now.date() and local_now.time() < DAY_FINAL_AT:
            continue
        trade_date = datetime(index.year, index.month, index.day, tzinfo=UTC)
        records.append(
            {
                "ticker": ticker,
                "date": trade_date,
                "open": float(row["Open"]),
                "high": float(row["High"]),
                "low": float(row["Low"]),
                "close": float(row["Close"]),
                "volume": int(row["Volume"]),
            }
        )
    return records


async def ingest_ticker(ticker: str, period: str = "2y") -> IngestResult:
    """Fetch and store OHLCV history for a single ticker.

    Failures are isolated per-ticker on purpose — one delisted/renamed
    ticker in a 20-ticker universe shouldn't abort the whole run.
    """
    try:
        history = await _fetch_history(ticker, period)

        if history.empty:
            return IngestResult(ticker, 0, error="No data returned")

        records = clean_history(ticker, history)
        upserted = await upsert_prices(records)
        return IngestResult(ticker, upserted)
    except Exception as exc:
        logger.exception("Failed to ingest %s", ticker)
        return IngestResult(ticker, 0, error=str(exc))


async def ingest_stock_universe(
    tickers: list[str], period: str = "2y"
) -> list[IngestResult]:
    results = []
    for ticker in tickers:
        result = await ingest_ticker(ticker, period=period)
        results.append(result)
        status = f"error: {result.error}" if result.error else "ok"
        logger.info(
            "Ingested %s: %d records upserted (%s)",
            result.source,
            result.records_upserted,
            status,
        )
    return results


async def catch_up(tickers: list[str], now: datetime | None = None) -> bool:
    """Ingest if stored prices are behind, e.g. the app was off at the daily
    run. On an exchange holiday nothing new exists, so tries are spaced out."""
    global _last_catch_up
    now = now or datetime.now(UTC)
    stored = await get_oldest_latest_date(tickers)
    if stored is not None and stored.date() >= last_final_weekday(now):
        return False
    if _last_catch_up is not None and now - _last_catch_up < CATCH_UP_RETRY:
        return False
    _last_catch_up = now
    logger.info("Stored prices end at %s; catching up", stored.date() if stored else "nothing")
    await ingest_stock_universe(tickers)
    return True
