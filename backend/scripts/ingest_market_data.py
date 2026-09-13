"""Manual entry point for market data ingestion.

Run from backend/ with the venv active:
    python -m scripts.ingest_market_data

This is a stand-in until Section 5 wires ingestion into a scheduled
background job — for now, it's how Phase 1's price data actually gets
into MongoDB.
"""

import asyncio
import logging

from app.core.constants import STOCK_UNIVERSE
from app.core.logging import configure_logging
from app.data.indexes import ensure_indexes
from app.data.mongo import close_mongo_connection, connect_to_mongo
from app.services.market_data_service import ingest_stock_universe

logger = logging.getLogger(__name__)


async def main() -> None:
    configure_logging()
    await connect_to_mongo()
    await ensure_indexes()

    try:
        results = await ingest_stock_universe(STOCK_UNIVERSE)
    finally:
        await close_mongo_connection()

    succeeded = [r for r in results if r.error is None]
    failed = [r for r in results if r.error is not None]
    total_records = sum(r.records_upserted for r in succeeded)

    logger.info(
        "Ingestion complete: %d/%d tickers succeeded, %d records upserted",
        len(succeeded),
        len(results),
        total_records,
    )
    if failed:
        logger.warning("Failed tickers: %s", [(r.ticker, r.error) for r in failed])


if __name__ == "__main__":
    asyncio.run(main())
