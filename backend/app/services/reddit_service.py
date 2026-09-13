"""Service layer for Reddit ingestion.

Seam between the external API (Reddit, via asyncpraw) and storage
(app/data/reddit_repository.py) — extraction/validation lives here.
"""

import logging
from datetime import datetime, timezone

import asyncpraw

from app.core.config import settings
from app.data.reddit_repository import upsert_reddit_posts
from app.services.ingestion_types import IngestResult

logger = logging.getLogger(__name__)


def _extract_submission_fields(submission: asyncpraw.models.Submission) -> dict:
    """Pull the fields we care about off a raw asyncpraw Submission."""
    return {
        "post_id": submission.id,
        "title": submission.title,
        "body": submission.selftext,
        "author": str(submission.author) if submission.author else None,
        "created_utc": submission.created_utc,
        "score": submission.score,
        "num_comments": submission.num_comments,
        "url": submission.url,
    }


def parse_submissions(subreddit_name: str, raw_posts: list[dict]) -> list[dict]:
    """Turn extracted submission dicts into clean, storage-ready records.

    Takes plain dicts (not real Submission objects) precisely so this can
    be unit tested with fabricated data, same pattern as news_service's
    parse_articles.
    """
    records = []
    for post in raw_posts:
        post_id = post.get("post_id")
        created_utc_raw = post.get("created_utc")
        # post_id is our dedup key, created_utc is what every "recent
        # posts" query sorts on — a post missing either isn't usable.
        if not post_id or created_utc_raw is None:
            continue

        records.append(
            {
                "post_id": post_id,
                "subreddit": subreddit_name,
                "title": post.get("title"),
                "body": post.get("body") or "",
                "author": post.get("author"),
                "created_utc": datetime.fromtimestamp(created_utc_raw, tz=timezone.utc),
                "score": post.get("score", 0),
                "num_comments": post.get("num_comments", 0),
                "url": post.get("url"),
            }
        )
    return records


async def fetch_posts_for_subreddit(
    reddit_client: asyncpraw.Reddit, subreddit_name: str, limit: int = 25
) -> list[dict]:
    subreddit = await reddit_client.subreddit(subreddit_name)
    raw_posts = [
        _extract_submission_fields(submission)
        async for submission in subreddit.new(limit=limit)
    ]
    return parse_submissions(subreddit_name, raw_posts)


async def ingest_posts_for_subreddit(
    reddit_client: asyncpraw.Reddit, subreddit_name: str
) -> IngestResult:
    """Fetch and store posts for a single subreddit.

    Failures are isolated per-subreddit, same reasoning as market data
    and news: one subreddit erroring out shouldn't abort the whole run.
    """
    try:
        records = await fetch_posts_for_subreddit(reddit_client, subreddit_name)
        if not records:
            return IngestResult(subreddit_name, 0, error="No posts found")

        upserted = await upsert_reddit_posts(records)
        return IngestResult(subreddit_name, upserted)
    except Exception as exc:
        logger.exception("Failed to ingest Reddit posts for r/%s", subreddit_name)
        return IngestResult(subreddit_name, 0, error=str(exc))


async def ingest_reddit_posts(subreddits: list[str]) -> list[IngestResult]:
    if not (settings.reddit_client_id and settings.reddit_client_secret and settings.reddit_user_agent):
        logger.warning(
            "Reddit API credentials are not set — skipping Reddit ingestion. "
            "Add REDDIT_CLIENT_ID/REDDIT_CLIENT_SECRET/REDDIT_USER_AGENT to backend/.env to enable this."
        )
        return []

    results = []
    reddit_client = asyncpraw.Reddit(
        client_id=settings.reddit_client_id,
        client_secret=settings.reddit_client_secret,
        user_agent=settings.reddit_user_agent,
    )
    try:
        for subreddit_name in subreddits:
            result = await ingest_posts_for_subreddit(reddit_client, subreddit_name)
            results.append(result)
            status = f"error: {result.error}" if result.error else "ok"
            logger.info(
                "Ingested r/%s: %d posts upserted (%s)",
                subreddit_name,
                result.records_upserted,
                status,
            )
    finally:
        await reddit_client.close()
    return results
