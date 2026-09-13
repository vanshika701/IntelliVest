"""Integration test — proves upsert_reddit_posts updates a post in place
on re-ingestion (e.g. score/num_comments changed) instead of duplicating.
"""

from datetime import UTC, datetime

from app.data.collections import get_reddit_collection
from app.data.reddit_repository import upsert_reddit_posts


async def test_upsert_reddit_posts_updates_in_place_instead_of_duplicating(mongo_test_db) -> None:
    post = {
        "post_id": "abc123",
        "subreddit": "stocks",
        "title": "Thoughts on Reliance Q3?",
        "body": "Discussion body",
        "author": "some_user",
        "created_utc": datetime(2026, 1, 1, tzinfo=UTC),
        "score": 10,
        "num_comments": 2,
        "url": "https://reddit.com/r/stocks/abc123",
    }

    first_pass_count = await upsert_reddit_posts([post])
    assert first_pass_count == 1

    # Re-ingesting the same post later, after it's gained upvotes/comments.
    updated_post = {**post, "score": 55, "num_comments": 9}
    second_pass_count = await upsert_reddit_posts([updated_post])
    assert second_pass_count == 1

    stored = await get_reddit_collection().find({"post_id": "abc123"}).to_list(length=None)
    assert len(stored) == 1
    assert stored[0]["score"] == 55
    assert stored[0]["num_comments"] == 9
