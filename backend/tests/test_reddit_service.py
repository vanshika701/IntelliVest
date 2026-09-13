"""Unit test — exercises submission parsing alone, with fabricated
extracted-field dicts instead of real asyncpraw Submission objects."""

from datetime import timezone

from app.services.reddit_service import parse_submissions


def test_parse_submissions_skips_entries_missing_post_id_or_created_utc() -> None:
    raw_posts = [
        {
            "post_id": "abc123",
            "title": "Thoughts on Reliance Q3?",
            "body": "Discussion body",
            "author": "some_user",
            "created_utc": 1735689600.0,
            "score": 42,
            "num_comments": 7,
            "url": "https://reddit.com/r/stocks/abc123",
        },
        {
            # Missing post_id — can't dedupe on this, must be skipped.
            "title": "Untraceable post",
            "created_utc": 1735689600.0,
        },
        {
            "post_id": "def456",
            "title": "No timestamp",
            # Missing created_utc — can't sort/query on this, must be skipped.
        },
    ]

    records = parse_submissions("stocks", raw_posts)

    assert len(records) == 1
    record = records[0]
    assert record["post_id"] == "abc123"
    assert record["subreddit"] == "stocks"
    assert record["created_utc"].tzinfo == timezone.utc
    assert record["score"] == 42
