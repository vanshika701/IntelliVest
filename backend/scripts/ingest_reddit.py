"""Manual entry point for Reddit ingestion.

Run from backend/ with the venv active:
    python -m scripts.ingest_reddit

Requires REDDIT_CLIENT_ID, REDDIT_CLIENT_SECRET, and REDDIT_USER_AGENT set
in backend/.env — without them, this logs a warning and exits cleanly
rather than failing. Get credentials at https://www.reddit.com/prefs/apps
(create a "script" type app).
"""

import asyncio
import logging

from app.core.constants import FINANCE_SUBREDDITS
from app.core.logging import configure_logging
from app.data.indexes import ensure_indexes
from app.data.mongo import close_mongo_connection, connect_to_mongo
from app.services.reddit_service import ingest_reddit_posts

logger = logging.getLogger(__name__)


async def main() -> None:
    configure_logging()
    await connect_to_mongo()
    await ensure_indexes()

    try:
        results = await ingest_reddit_posts(FINANCE_SUBREDDITS)
    finally:
        await close_mongo_connection()

    if not results:
        return

    succeeded = [r for r in results if r.error is None]
    failed = [r for r in results if r.error is not None]
    total_records = sum(r.records_upserted for r in succeeded)

    logger.info(
        "Reddit ingestion complete: %d/%d subreddits succeeded, %d posts upserted",
        len(succeeded),
        len(results),
        total_records,
    )
    if failed:
        logger.warning("Failed subreddits: %s", [(r.source, r.error) for r in failed])


if __name__ == "__main__":
    asyncio.run(main())
