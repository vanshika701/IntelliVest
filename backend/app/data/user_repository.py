"""Data-access layer for the `users` collection."""

from datetime import UTC, date, datetime

from app.data.collections import get_users_collection


async def find_user_by_email(email: str) -> dict | None:
    """Look up a user by their email address (case-insensitive)."""
    return await get_users_collection().find_one({"email": email.lower()})


async def find_user_by_id(user_id: str) -> dict | None:
    from bson import ObjectId

    return await get_users_collection().find_one({"_id": ObjectId(user_id)})


async def create_user(email: str, hashed_password: str, full_name: str, date_of_birth: date) -> str:
    """Insert a new user and return their string ID."""
    doc = {
        "email": email.lower(),
        "hashed_password": hashed_password,
        "full_name": full_name,
        # ISO text: BSON has no plain date, and a birthday has no timezone.
        "date_of_birth": date_of_birth.isoformat(),
        "created_at": datetime.now(UTC),
    }
    result = await get_users_collection().insert_one(doc)
    return str(result.inserted_id)


async def set_password(user_id: str, hashed_password: str) -> None:
    from bson import ObjectId

    await get_users_collection().update_one(
        {"_id": ObjectId(user_id)}, {"$set": {"hashed_password": hashed_password}}
    )


async def set_date_of_birth_once(user_id: str, date_of_birth: date) -> bool:
    """False if one is already stored: it can't be swapped to take over an account."""
    from bson import ObjectId

    result = await get_users_collection().update_one(
        {"_id": ObjectId(user_id), "date_of_birth": None},
        {"$set": {"date_of_birth": date_of_birth.isoformat()}},
    )
    return result.modified_count == 1
