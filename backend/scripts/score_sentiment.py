"""Manual entry point for FinBERT sentiment scoring.

Run from backend/ with the venv active:
    python -m scripts.score_sentiment

Scores every stored news article not yet scored by the configured model
(SENTIMENT_MODEL, default ProsusAI/finbert). The first run downloads the
model (~420 MB) into ml/models/hf_cache/.
"""

import asyncio

from app.core.logging import configure_logging
from app.data.indexes import ensure_indexes
from app.data.mongo import close_mongo_connection, connect_to_mongo
from app.services.sentiment_service import score_pending_articles


async def main() -> None:
    configure_logging()
    await connect_to_mongo()
    await ensure_indexes()
    try:
        await score_pending_articles()
    finally:
        await close_mongo_connection()


if __name__ == "__main__":
    asyncio.run(main())
