"""Index definitions for every collection, created once at app startup.

Each index here maps to a real query pattern a later phase needs — this
isn't "index everything just in case." Called from main.py's lifespan on
startup; `create_index` is idempotent, so re-running this on every restart
is safe and cheap once the indexes already exist.
"""

import logging

from app.data.collections import (
    get_alerts_collection,
    get_expenses_collection,
    get_news_collection,
    get_prices_collection,
    get_reddit_collection,
    get_users_collection,
    get_watchlist_collection,
)

logger = logging.getLogger(__name__)


async def ensure_indexes() -> None:
    prices = get_prices_collection()
    # One document per (ticker, date) — this is what makes ingestion
    # idempotent: re-running a pull for a day that's already stored
    # upserts in place instead of creating a duplicate row.
    await prices.create_index(
        [("ticker", 1), ("date", 1)],
        name="uniq_ticker_date",
        unique=True,
    )

    news = get_news_collection()
    # Dedup key — the same article shouldn't be stored twice even if two
    # ingestion runs both see it. Sparse because not every source is
    # guaranteed to give us a clean, unique URL.
    await news.create_index("url", name="uniq_url", unique=True, sparse=True)
    # Supports "recent news for ticker X" — the actual access pattern the
    # dashboard and Phase 5 sentiment pipeline need.
    await news.create_index(
        [("tickers", 1), ("published_at", -1)],
        name="tickers_published_at",
    )

    reddit = get_reddit_collection()
    # Reddit's own post ID is our dedup key.
    await reddit.create_index("post_id", name="uniq_post_id", unique=True)
    # Supports "recent posts in subreddit X" — mirrors the news pattern.
    await reddit.create_index(
        [("subreddit", 1), ("created_utc", -1)],
        name="subreddit_created_utc",
    )

    # --- Phase 2 collections ---

    users = get_users_collection()
    # Email is the login identifier — must be unique across users.
    await users.create_index("email", name="uniq_email", unique=True)

    expenses = get_expenses_collection()
    # "All expenses for user X in a date range" — the most common budget
    # query pattern: filtering by user_id then sorting/ranging by date.
    await expenses.create_index(
        [("user_id", 1), ("date", -1)],
        name="user_expenses_by_date",
    )

    watchlist = get_watchlist_collection()
    # A user can only have a ticker in their watchlist once.
    await watchlist.create_index(
        [("user_id", 1), ("ticker", 1)],
        name="uniq_user_ticker",
        unique=True,
    )

    alerts = get_alerts_collection()
    # "All active alerts for user X" — the dashboard and alert-check job
    # both need this.
    await alerts.create_index(
        [("user_id", 1), ("is_active", 1)],
        name="user_active_alerts",
    )
    # The background alert-check job needs to find all active alerts
    # for a given ticker quickly (check price against all users' rules).
    await alerts.create_index(
        [("ticker", 1), ("is_active", 1)],
        name="ticker_active_alerts",
    )

    logger.info(
        "MongoDB indexes ensured (prices, news_articles, reddit_posts, "
        "users, expenses, watchlist, alerts)"
    )

