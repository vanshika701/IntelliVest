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
        # Like tickers, sector tags from several searches add up.
        sectors = record.get("sectors", [])
        scalar_fields = {k: v for k, v in record.items() if k not in ("tickers", "sectors")}
        add = {"tickers": {"$each": tickers}}
        if sectors:
            add["sectors"] = {"$each": sectors}
        operations.append(
            UpdateOne(
                {"url": record["url"]},
                {
                    "$set": {**scalar_fields, "ingested_at": now},
                    "$addToSet": add,
                },
                upsert=True,
            )
        )

    result = await get_news_collection().bulk_write(operations, ordered=False)
    return result.upserted_count + result.modified_count


async def find_articles_needing_sentiment(model: str, limit: int, field: str = "sentiment") -> list[dict]:
    """Newest-first articles whose `field` wasn't scored by `model` — covers
    both never-scored articles and ones scored by an older model. `field` is
    "sentiment" for the default model, "sentiments.<key>" for the others."""
    cursor = (
        get_news_collection()
        .find({f"{field}.model": {"$ne": model}}, {"_id": 1, "title": 1, "description": 1})
        .sort("published_at", -1)
        .limit(limit)
    )
    return await cursor.to_list(length=limit)


async def set_article_sentiments(updates: list[tuple[ObjectId, dict]], field: str = "sentiment") -> int:
    if not updates:
        return 0
    operations = [UpdateOne({"_id": _id}, {"$set": {field: s}}) for _id, s in updates]
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


async def get_scored_articles_for_ticker(ticker: str, since: datetime, field: str = "sentiment") -> list[dict]:
    """Scored articles for one ticker since `since`, newest first, with the
    score from `field` returned as "sentiment" (see find_articles_needing_sentiment).
    Served by the (tickers, published_at) index."""
    cursor = get_news_collection().find(
        {"tickers": ticker, "published_at": {"$gte": since}, field: {"$exists": True}},
        {"_id": 0, "url": 1, "title": 1, "source": 1, "published_at": 1, field: 1},
    ).sort("published_at", -1)
    docs = await cursor.to_list(length=None)
    if field != "sentiment":
        parent, key = field.split(".", 1)
        for doc in docs:
            doc["sentiment"] = doc.pop(parent)[key]
    return docs


_HEADLINE_FIELDS = {
    "_id": 0, "url": 1, "title": 1, "source": 1, "published_at": 1, "tickers": 1, "sentiment": 1,
}  # fmt: skip


async def get_sector_headlines(sector: str, since: datetime, limit: int) -> list[dict]:
    """Articles found by the sector's own search, newest first."""
    cursor = (
        get_news_collection()
        .find({"sectors": sector, "published_at": {"$gte": since}}, _HEADLINE_FIELDS)
        .sort("published_at", -1)
        .limit(limit)
    )
    return await cursor.to_list(length=limit)


async def get_headlines_for_tickers(tickers: list[str], since: datetime, limit: int) -> list[dict]:
    cursor = (
        get_news_collection()
        .find({"tickers": {"$in": tickers}, "published_at": {"$gte": since}}, _HEADLINE_FIELDS)
        .sort("published_at", -1)
        .limit(limit)
    )
    return await cursor.to_list(length=limit)
