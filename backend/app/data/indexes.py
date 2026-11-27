"""Index definitions for every collection, created once at app startup.

Each index here maps to a real query pattern a later phase needs — this
isn't "index everything just in case." Called from main.py's lifespan on
startup; `create_index` is idempotent, so re-running this on every restart
is safe and cheap once the indexes already exist.
"""

import logging

from app.data.collections import (
    get_advice_collection,
    get_alerts_collection,
    get_budget_profiles_collection,
    get_chain_events_collection,
    get_chain_state_collection,
    get_chain_tasks_collection,
    get_expenses_collection,
    get_investments_collection,
    get_market_stats_collection,
    get_news_collection,
    get_prices_collection,
    get_recommendations_collection,
    get_reddit_collection,
    get_risk_profiles_collection,
    get_savings_goals_collection,
    get_sector_snapshots_collection,
    get_stock_predictions_collection,
    get_users_collection,
    get_wallet_challenges_collection,
    get_wallet_links_collection,
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

    # Sector-wide headlines (Phase 6).
    await news.create_index([("sectors", 1), ("published_at", -1)], name="sectors_published_at")

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

    investments = get_investments_collection()
    # "My investments", newest first — the only read pattern so far.
    await investments.create_index(
        [("user_id", 1), ("created_at", -1)],
        name="user_investments_by_created",
    )

    # --- Phase 8 collections ---
    # One budget profile per user.
    await get_budget_profiles_collection().create_index(
        "user_id", name="uniq_budget_profile_user", unique=True
    )
    # "My goals", oldest first.
    await get_savings_goals_collection().create_index(
        [("user_id", 1), ("created_at", 1)], name="user_goals_by_created"
    )

    # --- Phase 6 ---
    await get_sector_snapshots_collection().create_index("sector", name="uniq_sector", unique=True)

    # --- Phase 4 ---
    # One prediction per stock, day and horizon; reruns replace it. Reads
    # take a ticker's newest as_of.
    await get_stock_predictions_collection().create_index(
        [("ticker", 1), ("as_of", -1), ("horizon_days", 1)], name="uniq_ticker_asof_horizon", unique=True
    )

    # --- Phase 7 ---
    # One risk profile per user.
    await get_risk_profiles_collection().create_index(
        "user_id", name="uniq_risk_profile_user", unique=True
    )
    # One statistics document per price date; "latest" sorts on it.
    await get_market_stats_collection().create_index("as_of", name="uniq_as_of", unique=True)
    # "My latest recommendation", newest first.
    await get_recommendations_collection().create_index(
        [("user_id", 1), ("created_at", -1)], name="user_recommendations_by_created"
    )

    # --- Phase 10 (blockchain); empty unless BLOCKCHAIN_ENABLED ---
    # One wallet per user and one user per wallet.
    links = get_wallet_links_collection()
    await links.create_index("user_id", name="uniq_wallet_user", unique=True)
    await links.create_index("address", name="uniq_wallet_address", unique=True)
    # One live challenge per user; Mongo deletes it once expired.
    challenges = get_wallet_challenges_collection()
    await challenges.create_index("user_id", name="uniq_challenge_user", unique=True)
    await challenges.create_index("expires_at", name="challenge_ttl", expireAfterSeconds=0)
    tasks = get_chain_tasks_collection()
    # "My AI trades", newest first.
    await tasks.create_index([("user_id", 1), ("created_at", -1)], name="user_tasks_by_created")
    # An on-chain task maps to one document.
    await tasks.create_index(
        "task_id", name="uniq_task_id", unique=True, partialFilterExpression={"task_id": {"$type": "string"}}
    )
    # At most one unfinished task per user and fund, so a double click can't queue two trades.
    await tasks.create_index(
        [("user_id", 1), ("fund", 1)],
        name="uniq_active_task",
        unique=True,
        partialFilterExpression={"active": True},
    )
    # The worker's queue.
    await tasks.create_index([("active", 1), ("next_attempt_at", 1)], name="task_queue")
    # Each log once, however often the reader rescans a block.
    events = get_chain_events_collection()
    await events.create_index(
        [("tx_hash", 1), ("log_index", 1)], name="uniq_tx_log", unique=True
    )
    await events.create_index("block_number", name="events_by_block")
    await get_chain_state_collection().create_index("key", name="uniq_state_key", unique=True)

    # --- Phase 9 ---
    # "My latest advice", newest first.
    await get_advice_collection().create_index(
        [("user_id", 1), ("created_at", -1)], name="user_advice_by_created"
    )

    logger.info(
        "MongoDB indexes ensured (prices, news_articles, reddit_posts, "
        "users, expenses, watchlist, alerts, investments, budget_profiles, savings_goals, "
        "sector_snapshots, stock_predictions, risk_profiles, market_stats, recommendations, blockchain, advice)"
    )

