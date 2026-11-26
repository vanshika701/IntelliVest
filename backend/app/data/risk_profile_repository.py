"""Data access for Phase 7 risk profiles: one document per user."""

from pymongo import ReturnDocument

from app.data.collections import get_risk_profiles_collection


async def get_risk_profile(user_id: str) -> dict | None:
    return await get_risk_profiles_collection().find_one({"user_id": user_id}, {"_id": 0})


async def upsert_risk_profile(user_id: str, data: dict) -> dict:
    return await get_risk_profiles_collection().find_one_and_update(
        {"user_id": user_id},
        {"$set": {**data, "user_id": user_id}},
        upsert=True,
        return_document=ReturnDocument.AFTER,
        projection={"_id": 0},
    )
