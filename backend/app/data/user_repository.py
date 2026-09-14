"""Data-access layer for the `users` collection."""

from datetime import UTC, datetime

from app.data.collections import get_users_collection


async def find_user_by_email(email: str) -> dict | None:
    """Look up a user by their email address (case-insensitive)."""
    return await get_users_collection().find_one({"email": email.lower()})


async def find_user_by_id(user_id: str) -> dict | None:
    from bson import ObjectId

    return await get_users_collection().find_one({"_id": ObjectId(user_id)})


async def create_user(email: str, hashed_password: str, full_name: str) -> str:
    """Insert a new user and return their string ID."""
    doc = {
        "email": email.lower(),
        "hashed_password": hashed_password,
        "full_name": full_name,
        "created_at": datetime.now(UTC),
    }
    result = await get_users_collection().insert_one(doc)
    return str(result.inserted_id)
