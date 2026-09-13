"""Data-access layer for the `news_articles` collection.

Unlike prices, the same article can legitimately come back from more than
one ticker's search (e.g. a broad market story mentions both Reliance and
TCS) — so upserting here has to *merge* the tickers list on a duplicate
`url`, not overwrite it, or the second ingestion run would erase the
first ticker's association.
"""

from datetime import datetime, timezone

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

    now = datetime.now(timezone.utc)
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
