"""Data-access layer for the `investments` collection (mock one-time
orders and SIPs — no real money moves)."""

from bson import ObjectId
from bson.errors import InvalidId
from pymongo import ReturnDocument

from app.data.collections import get_investments_collection


def _to_object_id(investment_id: str) -> ObjectId | None:
    try:
        return ObjectId(investment_id)
    except (InvalidId, TypeError):
        return None


def _serialize(doc: dict) -> dict:
    doc["id"] = str(doc.pop("_id"))
    return doc


async def insert_investment(doc: dict) -> dict:
    result = await get_investments_collection().insert_one(doc)
    return _serialize({**doc, "_id": result.inserted_id})


async def get_user_investment(user_id: str, investment_id: str) -> dict | None:
    oid = _to_object_id(investment_id)
    if oid is None:
        return None
    doc = await get_investments_collection().find_one({"_id": oid, "user_id": user_id})
    return _serialize(doc) if doc else None


async def update_investment_if_status(
    user_id: str, investment_id: str, expected_status: str, changes: dict
) -> dict | None:
    """Apply `changes` only if the investment is still in `expected_status`
    — makes payment results one-shot even if a client retries."""
    oid = _to_object_id(investment_id)
    if oid is None:
        return None
    doc = await get_investments_collection().find_one_and_update(
        {"_id": oid, "user_id": user_id, "status": expected_status},
        {"$set": changes},
        return_document=ReturnDocument.AFTER,
    )
    return _serialize(doc) if doc else None


async def list_user_investments(user_id: str, limit: int = 100) -> list[dict]:
    cursor = get_investments_collection().find({"user_id": user_id}).sort("created_at", -1).limit(limit)
    return [_serialize(doc) for doc in await cursor.to_list(length=limit)]


async def list_held_investments(user_id: str) -> list[dict]:
    """Paid one-time orders and active SIPs, oldest first."""
    cursor = get_investments_collection().find(
        {"user_id": user_id, "status": {"$in": ["completed", "active"]}}
    ).sort("created_at", 1)
    return [_serialize(doc) for doc in await cursor.to_list(length=None)]
