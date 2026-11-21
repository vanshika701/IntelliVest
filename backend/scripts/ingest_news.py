"""Manual entry point for news ingestion.

Run from backend/ with the venv active:
    python -m scripts.ingest_news

Pulls from public RSS feeds — no API key needed.
"""

import asyncio
import logging

from app.core.constants import STOCK_UNIVERSE
from app.core.logging import configure_logging
from app.data.indexes import ensure_indexes
from app.data.mongo import close_mongo_connection, connect_to_mongo
from app.services.news_service import ingest_news_for_universe

logger = logging.getLogger(__name__)


async def main() -> None:
    configure_logging()
    await connect_to_mongo()
    await ensure_indexes()

    try:
        results = await ingest_news_for_universe(STOCK_UNIVERSE)
    finally:
        await close_mongo_connection()

    succeeded = [r for r in results if r.error is None]
    failed = [r for r in results if r.error is not None]
    total_records = sum(r.records_upserted for r in succeeded)

    logger.info(
        "News ingestion complete: %d/%d feeds succeeded, %d articles upserted",
        len(succeeded),
        len(results),
        total_records,
    )
    if failed:
        logger.warning("Failed feeds: %s", [(r.source, r.error) for r in failed])


if __name__ == "__main__":
    asyncio.run(main())
