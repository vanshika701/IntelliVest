"""Data-access layer for the `news_articles` collection.

Unlike prices, the same article can legitimately come back from more than
one ticker's search (e.g. a broad market story mentions both Reliance and
TCS) — so upserting here has to *merge* the tickers list on a duplicate
`url`, not overwrite it, or the second ingestion run would erase the
first ticker's association.
"""

from datetime import UTC, datetime

from bson import ObjectId
from pymongo import UpdateOne

from app.data.collections import get_news_collection


async def upsert_news_articles(records: list[dict]) -> int:
    """Upsert news articles, keyed on `url`.

    Scalar fields (title, description, ...) are set as-is; `tickers` is
    merged with $addToSet so an article already stored from one ticker's
    search gains the new ticker instead of losing the old one.
    """
    if not records:
        return 0

    now = datetime.now(UTC)
    operations = []
    for record in records:
        tickers = record["tickers"]
        scalar_fields = {k: v for k, v in record.items() if k != "tickers"}
        operations.append(
            UpdateOne(
                {"url": record["url"]},
                {
                    "$set": {**scalar_fields, "ingested_at": now},
                    "$addToSet": {"tickers": {"$each": tickers}},
                },
                upsert=True,
            )
        )

    result = await get_news_collection().bulk_write(operations, ordered=False)
    return result.upserted_count + result.modified_count


async def find_articles_needing_sentiment(model: str, limit: int) -> list[dict]:
    """Newest-first articles not yet scored by `model` — covers both
    never-scored articles and ones scored by an older model."""
    cursor = (
        get_news_collection()
        .find({"sentiment.model": {"$ne": model}}, {"_id": 1, "title": 1, "description": 1})
        .sort("published_at", -1)
        .limit(limit)
    )
    return await cursor.to_list(length=limit)


async def set_article_sentiments(updates: list[tuple[ObjectId, dict]]) -> int:
    if not updates:
        return 0
    operations = [UpdateOne({"_id": _id}, {"$set": {"sentiment": s}}) for _id, s in updates]
    result = await get_news_collection().bulk_write(operations, ordered=False)
    return result.modified_count


async def get_recent_articles_for_ticker(ticker: str, since: datetime, limit: int = 40) -> list[dict]:
    """Stored articles for one ticker since `since`, newest first (scored
    or not). Served by the (tickers, published_at) index."""
    cursor = (
        get_news_collection()
        .find(
            {"tickers": ticker, "published_at": {"$gte": since}},
            {"_id": 0, "url": 1, "title": 1, "description": 1, "source": 1, "published_at": 1},
        )
        .sort("published_at", -1)
        .limit(limit)
    )
    return await cursor.to_list(length=limit)


async def get_scored_articles_for_ticker(ticker: str, since: datetime) -> list[dict]:
    """Scored articles for one ticker since `since`, newest first. Served
    by the (tickers, published_at) index."""
    cursor = get_news_collection().find(
        {"tickers": ticker, "published_at": {"$gte": since}, "sentiment": {"$exists": True}},
        {"_id": 0, "url": 1, "title": 1, "source": 1, "published_at": 1, "sentiment": 1},
    ).sort("published_at", -1)
    return await cursor.to_list(length=None)
