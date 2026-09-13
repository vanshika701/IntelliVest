"""Data-access layer: owns the MongoDB connection.

Nothing outside this module should import motor directly — services ask
this module for a database handle, so the connection lifecycle (and the
driver itself, if it ever changed) stays in one place.
"""

import logging

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

from app.core.config import settings

logger = logging.getLogger(__name__)

_client: AsyncIOMotorClient | None = None


async def connect_to_mongo() -> None:
    """Open the MongoDB connection. Called once on app startup."""
    global _client
    _client = AsyncIOMotorClient(settings.mongodb_uri)
    logger.info("MongoDB client created for %s", settings.mongodb_uri)


async def close_mongo_connection() -> None:
    """Close the MongoDB connection. Called once on app shutdown."""
    global _client
    if _client is not None:
        _client.close()
        _client = None
        logger.info("MongoDB client closed")


def get_database() -> AsyncIOMotorDatabase:
    """Return the app's database handle.

    Raises if called before connect_to_mongo() has run — that's a bug
    (something used the DB outside the app's lifespan), not something to
    silently paper over.
    """
    if _client is None:
        raise RuntimeError("MongoDB client is not initialized. Call connect_to_mongo() first.")
    return _client[settings.mongodb_db_name]


async def ping_database() -> bool:
    """Check the DB is actually reachable, for use in health checks."""
    try:
        await get_database().command("ping")
        return True
    except Exception:
        logger.exception("MongoDB ping failed")
        return False
