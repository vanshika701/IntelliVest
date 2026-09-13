"""Integration test — proves upsert_news_articles merges tickers on a
duplicate url instead of overwriting, which is what lets the same article
correctly show up under every ticker it's actually relevant to.
"""

from datetime import UTC, datetime

from app.data.collections import get_news_collection
from app.data.news_repository import upsert_news_articles


async def test_upsert_news_articles_merges_tickers_on_duplicate_url(mongo_test_db) -> None:
    article = {
        "url": "https://example.com/shared-market-story",
        "title": "Markets rally on rate-cut hopes",
        "description": "desc",
        "content": "content",
        "source": "Example News",
        "published_at": datetime(2026, 1, 1, tzinfo=UTC),
        "tickers": ["RELIANCE.NS"],
    }

    first_pass_count = await upsert_news_articles([article])
    assert first_pass_count == 1

    # A second ingestion run finds the same article while searching for a
    # different ticker — it should gain that ticker, not replace the first.
    second_article = {**article, "tickers": ["TCS.NS"]}
    second_pass_count = await upsert_news_articles([second_article])
    assert second_pass_count == 1

    stored = await get_news_collection().find_one({"url": article["url"]})
    assert set(stored["tickers"]) == {"RELIANCE.NS", "TCS.NS"}
