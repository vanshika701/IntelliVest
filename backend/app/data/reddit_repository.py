"""Data-access layer for the `reddit_posts` collection."""

from datetime import datetime, timezone

from pymongo import UpdateOne

from app.data.collections import get_reddit_collection


async def upsert_reddit_posts(records: list[dict]) -> int:
    """Upsert Reddit posts, keyed on post_id.

    Unlike news, a post belongs to exactly one subreddit forever, so a
    plain overwrite on duplicate is correct here — no merge needed like
    news_repository's tickers list.
    """
    if not records:
        return 0

    now = datetime.now(timezone.utc)
    operations = [
        UpdateOne(
            {"post_id": record["post_id"]},
            {"$set": {**record, "ingested_at": now}},
            upsert=True,
        )
        for record in records
    ]

    result = await get_reddit_collection().bulk_write(operations, ordered=False)
    return result.upserted_count + result.modified_count
