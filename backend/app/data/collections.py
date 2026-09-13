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
