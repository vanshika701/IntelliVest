"""Data-access layer for the `watchlist` collection."""

from datetime import UTC, datetime

from bson import ObjectId
from pymongo.errors import DuplicateKeyError

from app.data.collections import get_watchlist_collection


async def add_watchlist_item(user_id: str, item: dict) -> str | None:
    """Insert a watchlist item. Returns ID, or None if duplicate (user+ticker)."""
    doc = {
        **item,
        "user_id": user_id,
        "added_at": datetime.now(UTC),
    }
    try:
        result = await get_watchlist_collection().insert_one(doc)
        return str(result.inserted_id)
    except DuplicateKeyError:
        return None


async def get_watchlist_for_user(user_id: str) -> list[dict]:
    """Return all watchlist items for a user, newest first."""
    cursor = get_watchlist_collection().find({"user_id": user_id}).sort("added_at", -1)
    return await cursor.to_list(length=200)


async def update_watchlist_item(user_id: str, item_id: str, updates: dict) -> bool:
    """Patch fields on a watchlist item if it belongs to the user."""
    # Only include non-None fields in the $set — callers send partial updates.
    set_doc = {k: v for k, v in updates.items() if v is not None}
    if not set_doc:
        return False
    result = await get_watchlist_collection().update_one(
        {"_id": ObjectId(item_id), "user_id": user_id},
        {"$set": set_doc},
    )
    return result.modified_count > 0


async def remove_watchlist_item(user_id: str, item_id: str) -> bool:
    """Delete a watchlist item if it belongs to the user."""
    result = await get_watchlist_collection().delete_one(
        {"_id": ObjectId(item_id), "user_id": user_id}
    )
    return result.deleted_count > 0
