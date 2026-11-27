"""Data access for Phase 10: wallet links, link challenges, AI trade tasks,
chain events and the event reader's position.

Addresses are stored lower-case so lookups don't depend on checksum case.
"""

from datetime import datetime

from bson import ObjectId
from bson.errors import InvalidId
from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

from app.data.collections import (
    get_chain_events_collection,
    get_chain_state_collection,
    get_chain_tasks_collection,
    get_wallet_challenges_collection,
    get_wallet_links_collection,
)

# --- Wallet links ---


async def get_wallet_link(user_id: str) -> dict | None:
    return await get_wallet_links_collection().find_one({"user_id": user_id}, {"_id": 0})


async def get_wallet_link_by_address(address: str) -> dict | None:
    return await get_wallet_links_collection().find_one({"address": address.lower()}, {"_id": 0})


async def insert_wallet_link(user_id: str, address: str, linked_at: datetime) -> bool:
    """False when the user already has a wallet or the wallet has a user."""
    try:
        await get_wallet_links_collection().insert_one(
            {"user_id": user_id, "address": address.lower(), "linked_at": linked_at}
        )
    except DuplicateKeyError:
        return False
    return True


async def delete_wallet_link(user_id: str) -> bool:
    result = await get_wallet_links_collection().delete_one({"user_id": user_id})
    return result.deleted_count > 0


# --- Link challenges (one-time) ---


async def put_challenge(user_id: str, address: str, message: str, expires_at: datetime) -> None:
    """Replaces any earlier challenge, so only the newest one can be used."""
    await get_wallet_challenges_collection().replace_one(
        {"user_id": user_id},
        {
            "user_id": user_id,
            "address": address.lower(),
            "message": message,
            "expires_at": expires_at,
        },
        upsert=True,
    )


async def take_challenge(user_id: str, address: str, now: datetime) -> dict | None:
    """Removes and returns the live challenge; a second call gets None."""
    return await get_wallet_challenges_collection().find_one_and_delete(
        {"user_id": user_id, "address": address.lower(), "expires_at": {"$gt": now}}
    )


# --- AI trade tasks ---


async def insert_task(doc: dict) -> str | None:
    """None when the user already has an unfinished task for this fund."""
    try:
        result = await get_chain_tasks_collection().insert_one(doc)
    except DuplicateKeyError:
        return None
    return str(result.inserted_id)


async def list_tasks(user_id: str, limit: int = 50) -> list[dict]:
    cursor = get_chain_tasks_collection().find({"user_id": user_id}).sort("created_at", -1)
    return await cursor.to_list(length=limit)


async def get_task(user_id: str, doc_id: str) -> dict | None:
    try:
        oid = ObjectId(doc_id)
    except InvalidId:
        return None
    return await get_chain_tasks_collection().find_one({"_id": oid, "user_id": user_id})


async def get_task_by_chain_id(task_id: str) -> dict | None:
    return await get_chain_tasks_collection().find_one({"task_id": task_id})


async def claim_next_task(now: datetime, lease_until: datetime) -> dict | None:
    """Takes the next due task and leases it, so two workers can't run it."""
    return await get_chain_tasks_collection().find_one_and_update(
        {
            "active": True,
            "next_attempt_at": {"$lte": now},
            "$or": [{"lease_until": None}, {"lease_until": {"$lte": now}}],
        },
        {"$set": {"lease_until": lease_until}},
        sort=[("next_attempt_at", 1)],
        return_document=ReturnDocument.AFTER,
    )


async def update_task(doc_id: ObjectId, fields: dict, push: dict | None = None) -> None:
    update: dict = {"$set": fields}
    if push:
        update["$push"] = push
    await get_chain_tasks_collection().update_one({"_id": doc_id}, update)


async def update_task_by_chain_id(task_id: str, fields: dict) -> bool:
    result = await get_chain_tasks_collection().update_one({"task_id": task_id}, {"$set": fields})
    return result.matched_count > 0


# --- Chain events and reader position ---


async def insert_event(doc: dict) -> bool:
    """False if this log was already stored."""
    try:
        await get_chain_events_collection().insert_one(doc)
    except DuplicateKeyError:
        return False
    return True


async def delete_events_from(block_number: int) -> int:
    """Drops events from reorganized blocks before they are read again."""
    result = await get_chain_events_collection().delete_many(
        {"block_number": {"$gte": block_number}}
    )
    return result.deleted_count


async def get_state(key: str) -> dict | None:
    return await get_chain_state_collection().find_one({"key": key}, {"_id": 0})


async def set_state(key: str, value: dict) -> None:
    await get_chain_state_collection().update_one(
        {"key": key}, {"$set": {"key": key, **value}}, upsert=True
    )
