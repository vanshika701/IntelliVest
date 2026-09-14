"""Data-access layer for the `alerts` collection."""

from datetime import UTC, datetime

from bson import ObjectId

from app.data.collections import get_alerts_collection


async def create_alert(user_id: str, alert: dict) -> str:
    """Insert a price proximity alert and return its string ID."""
    doc = {
        **alert,
        "user_id": user_id,
        "is_active": True,
        "triggered": False,
        "triggered_at": None,
        "created_at": datetime.now(UTC),
    }
    result = await get_alerts_collection().insert_one(doc)
    return str(result.inserted_id)


async def get_alerts_for_user(user_id: str) -> list[dict]:
    """Return all alerts for a user, newest first."""
    cursor = get_alerts_collection().find({"user_id": user_id}).sort("created_at", -1)
    return await cursor.to_list(length=200)


async def get_active_alerts_for_ticker(ticker: str) -> list[dict]:
    """Return all active (non-triggered) alerts targeting a given ticker."""
    cursor = get_alerts_collection().find({"ticker": ticker, "is_active": True})
    return await cursor.to_list(length=1000)


async def get_all_active_alerts() -> list[dict]:
    """Return every active alert across all users (for the background check job)."""
    cursor = get_alerts_collection().find({"is_active": True})
    return await cursor.to_list(length=5000)


async def mark_alert_triggered(alert_id: str) -> None:
    """Flag an alert as triggered."""
    await get_alerts_collection().update_one(
        {"_id": ObjectId(alert_id)},
        {"$set": {"triggered": True, "triggered_at": datetime.now(UTC)}},
    )


async def toggle_alert_active(user_id: str, alert_id: str, is_active: bool) -> bool:
    """Enable or disable an alert. Also resets trigger status if re-enabling."""
    update: dict = {"is_active": is_active}
    if is_active:
        update["triggered"] = False
        update["triggered_at"] = None
    result = await get_alerts_collection().update_one(
        {"_id": ObjectId(alert_id), "user_id": user_id},
        {"$set": update},
    )
    return result.modified_count > 0


async def delete_alert(user_id: str, alert_id: str) -> bool:
    """Delete an alert if it belongs to the user."""
    result = await get_alerts_collection().delete_one(
        {"_id": ObjectId(alert_id), "user_id": user_id}
    )
    return result.deleted_count > 0
