"""Data access for Phase 8: budget profiles, savings goals and the
monthly spend aggregation over `expenses`."""

from datetime import datetime

from bson import ObjectId
from bson.errors import InvalidId
from pymongo import ReturnDocument

from app.data.collections import (
    get_budget_profiles_collection,
    get_expenses_collection,
    get_savings_goals_collection,
)


def _oid(value: str) -> ObjectId | None:
    try:
        return ObjectId(value)
    except (InvalidId, TypeError):
        return None


async def get_profile(user_id: str) -> dict | None:
    return await get_budget_profiles_collection().find_one({"user_id": user_id}, {"_id": 0})


async def upsert_profile(user_id: str, data: dict) -> dict:
    return await get_budget_profiles_collection().find_one_and_update(
        {"user_id": user_id},
        {"$set": {**data, "user_id": user_id}},
        upsert=True,
        return_document=ReturnDocument.AFTER,
        projection={"_id": 0},
    )


async def insert_goal(doc: dict) -> dict:
    result = await get_savings_goals_collection().insert_one(doc)
    out = {**doc, "id": str(result.inserted_id)}
    out.pop("_id", None)
    return out


async def list_goals(user_id: str) -> list[dict]:
    cursor = get_savings_goals_collection().find({"user_id": user_id}).sort("created_at", 1)
    goals = []
    for doc in await cursor.to_list(length=100):
        doc["id"] = str(doc.pop("_id"))
        goals.append(doc)
    return goals


async def get_goal(user_id: str, goal_id: str) -> dict | None:
    oid = _oid(goal_id)
    if oid is None:
        return None
    doc = await get_savings_goals_collection().find_one({"_id": oid, "user_id": user_id})
    if doc:
        doc["id"] = str(doc.pop("_id"))
    return doc


async def delete_goal(user_id: str, goal_id: str) -> bool:
    oid = _oid(goal_id)
    if oid is None:
        return False
    result = await get_savings_goals_collection().delete_one({"_id": oid, "user_id": user_id})
    return result.deleted_count > 0


async def spend_by_category_and_month(user_id: str, since: datetime) -> list[dict]:
    """[{category, month: 'YYYY-MM', total}] for expense records since `since`."""
    pipeline = [
        {"$match": {"user_id": user_id, "expense_type": "expense", "date": {"$gte": since}}},
        {
            "$group": {
                "_id": {
                    "category": "$category",
                    "month": {"$dateToString": {"format": "%Y-%m", "date": "$date"}},
                },
                "total": {"$sum": "$amount"},
            }
        },
    ]
    rows = await get_expenses_collection().aggregate(pipeline).to_list(length=1000)
    return [{"category": r["_id"]["category"], "month": r["_id"]["month"], "total": r["total"]} for r in rows]
