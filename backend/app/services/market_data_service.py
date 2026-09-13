"""Service layer for market data ingestion.

This is the seam between the external API (yfinance, called here) and
storage (app/data/prices_repository.py, which owns the actual Mongo
write) — cleaning/validation logic belongs in this middle layer, not in
either of those.
"""

import asyncio
import logging

import pandas as pd
import yfinance as yf

from app.core.retry import with_retry
from app.data.prices_repository import upsert_prices
from app.services.ingestion_types import IngestResult

logger = logging.getLogger(__name__)


@with_retry
async def _fetch_history(ticker: str, period: str) -> pd.DataFrame:
    # yfinance's .history() is a blocking network call; run it on a
    # worker thread so it doesn't freeze the event loop this coroutine is
    # running on (this matters once ingestion runs inside the same
    # process as the API, driven by the scheduler below).
    return await asyncio.to_thread(yf.Ticker(ticker).history, period=period, interval="1d")


def clean_history(ticker: str, history: pd.DataFrame) -> list[dict]:
    """Turn yfinance's raw DataFrame into clean, storage-ready records."""
    # A row missing any OHLCV field isn't usable — better to drop it than
    # let a null silently corrupt an average or a backtest later.
    history = history.dropna(subset=["Open", "High", "Low", "Close", "Volume"])

    records = []
    for index, row in history.iterrows():
        # yfinance returns timestamps in the exchange's local timezone
        # (e.g. Asia/Kolkata for .NS tickers). Normalize to UTC midnight
        # so "date" means the same thing no matter which exchange a
        # ticker trades on — this is the timezone-handling step the
        # phase's "concepts to learn" calls out explicitly.
        trade_date = index.tz_convert("UTC").normalize().to_pydatetime()
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
