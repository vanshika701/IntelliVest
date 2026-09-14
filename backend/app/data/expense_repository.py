"""Data-access layer for the `expenses` collection."""

from datetime import UTC, datetime

from bson import ObjectId

from app.data.collections import get_expenses_collection


async def insert_expense(user_id: str, expense: dict) -> str:
    """Insert a single expense record and return its string ID."""
    doc = {
        **expense,
        "user_id": user_id,
        "created_at": datetime.now(UTC),
    }
    result = await get_expenses_collection().insert_one(doc)
    return str(result.inserted_id)


async def insert_many_expenses(records: list[dict]) -> int:
    """Bulk-insert expense records (used by CSV import). Returns count."""
    if not records:
        return 0
    result = await get_expenses_collection().insert_many(records)
    return len(result.inserted_ids)


async def get_expenses_for_user(
    user_id: str,
    skip: int = 0,
    limit: int = 50,
) -> list[dict]:
    """Return expenses for a user, newest first."""
    cursor = (
        get_expenses_collection()
        .find({"user_id": user_id})
        .sort("date", -1)
        .skip(skip)
        .limit(limit)
    )
    return await cursor.to_list(length=limit)


async def count_expenses_for_user(user_id: str) -> int:
    return await get_expenses_collection().count_documents({"user_id": user_id})


async def delete_expense(user_id: str, expense_id: str) -> bool:
    """Delete an expense if it belongs to the given user. Returns True if deleted."""
    result = await get_expenses_collection().delete_one(
        {"_id": ObjectId(expense_id), "user_id": user_id}
    )
    return result.deleted_count > 0


async def get_expense_summary(user_id: str) -> dict:
    """Aggregate total income, total expense, net, and per-category totals."""
    pipeline = [
        {"$match": {"user_id": user_id}},
        {
            "$group": {
                "_id": {"expense_type": "$expense_type", "category": "$category"},
                "total": {"$sum": "$amount"},
            }
        },
    ]
    cursor = get_expenses_collection().aggregate(pipeline)
    results = await cursor.to_list(length=500)

    total_income = 0.0
    total_expense = 0.0
    by_category: dict[str, float] = {}

    for row in results:
        exp_type = row["_id"]["expense_type"]
        category = row["_id"]["category"]
        total = row["total"]

        if exp_type == "income":
            total_income += total
        else:
            total_expense += total

        by_category[category] = by_category.get(category, 0.0) + total

    return {
        "total_income": total_income,
        "total_expense": total_expense,
        "net": total_income - total_expense,
        "by_category": by_category,
    }
