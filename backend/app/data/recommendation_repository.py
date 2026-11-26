"""Data access for Phase 7 `recommendations`: every recommendation is
kept with its inputs and versions, so a past suggestion can always be
explained (and later prefill Phase 10 mandates)."""

from app.data.collections import get_recommendations_collection


def _public(doc: dict) -> dict:
    doc["id"] = str(doc.pop("_id"))
    doc.pop("user_id", None)
    return doc


async def insert_recommendation(user_id: str, doc: dict) -> dict:
    stored = {**doc, "user_id": user_id}
    result = await get_recommendations_collection().insert_one(stored)
    return _public({**stored, "_id": result.inserted_id})


async def get_latest_recommendation(user_id: str) -> dict | None:
    doc = await get_recommendations_collection().find_one(
        {"user_id": user_id}, sort=[("created_at", -1)]
    )
    return _public(doc) if doc else None
