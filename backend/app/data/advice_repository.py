"""Data access for Phase 9 `advice`: every piece of advice is kept with the
module results it was built from, so it can be explained later and used as
evidence for Phase 10 trade proposals."""

from app.data.collections import get_advice_collection


def _public(doc: dict) -> dict:
    """API view: no user id, and no proposal salt (it would let anyone with
    the on-chain hashes test guesses about the user's amounts)."""
    doc["id"] = str(doc.pop("_id"))
    doc.pop("user_id", None)
    proposals = doc.get("proposals")
    if proposals:
        doc["proposals"] = {k: v for k, v in proposals.items() if k != "salt"}
    return doc


async def insert_advice(user_id: str, doc: dict) -> dict:
    stored = {**doc, "user_id": user_id}
    result = await get_advice_collection().insert_one(stored)
    return _public({**stored, "_id": result.inserted_id})


async def get_latest_advice(user_id: str) -> dict | None:
    doc = await get_advice_collection().find_one({"user_id": user_id}, sort=[("created_at", -1)])
    return _public(doc) if doc else None
