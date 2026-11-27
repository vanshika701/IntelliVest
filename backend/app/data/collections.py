"""Typed accessors for each MongoDB collection.

Every collection this app uses gets one function here — services ask for
`get_prices_collection()` etc. instead of doing `get_database()["prices"]`
inline, so the collection name is defined in exactly one place.
"""

from motor.motor_asyncio import AsyncIOMotorCollection

from app.data.mongo import get_database


def get_prices_collection() -> AsyncIOMotorCollection:
    return get_database()["prices"]


def get_news_collection() -> AsyncIOMotorCollection:
    return get_database()["news_articles"]


def get_reddit_collection() -> AsyncIOMotorCollection:
    return get_database()["reddit_posts"]


def get_sector_snapshots_collection() -> AsyncIOMotorCollection:
    return get_database()["sector_snapshots"]


def get_stock_predictions_collection() -> AsyncIOMotorCollection:
    return get_database()["stock_predictions"]


def get_users_collection() -> AsyncIOMotorCollection:
    return get_database()["users"]


def get_expenses_collection() -> AsyncIOMotorCollection:
    return get_database()["expenses"]


def get_watchlist_collection() -> AsyncIOMotorCollection:
    return get_database()["watchlist"]


def get_alerts_collection() -> AsyncIOMotorCollection:
    return get_database()["alerts"]


def get_investments_collection() -> AsyncIOMotorCollection:
    return get_database()["investments"]


def get_budget_profiles_collection() -> AsyncIOMotorCollection:
    return get_database()["budget_profiles"]


def get_savings_goals_collection() -> AsyncIOMotorCollection:
    return get_database()["savings_goals"]


def get_risk_profiles_collection() -> AsyncIOMotorCollection:
    return get_database()["risk_profiles"]


def get_market_stats_collection() -> AsyncIOMotorCollection:
    return get_database()["market_stats"]


def get_recommendations_collection() -> AsyncIOMotorCollection:
    return get_database()["recommendations"]


# --- Phase 10 (blockchain) ---


def get_wallet_links_collection() -> AsyncIOMotorCollection:
    return get_database()["wallet_links"]


def get_wallet_challenges_collection() -> AsyncIOMotorCollection:
    return get_database()["wallet_challenges"]


def get_chain_tasks_collection() -> AsyncIOMotorCollection:
    return get_database()["chain_tasks"]


def get_chain_events_collection() -> AsyncIOMotorCollection:
    return get_database()["chain_events"]


def get_chain_state_collection() -> AsyncIOMotorCollection:
    return get_database()["chain_state"]
