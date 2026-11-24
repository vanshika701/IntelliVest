"""Tests for mapping old free-text / ML category labels onto the fixed list."""

from datetime import UTC, datetime

import pytest

from app.core.budget_config import CATEGORIES
from app.data.collections import get_expenses_collection
from app.services.category_migration import map_legacy_category, migrate_expense_categories


@pytest.mark.parametrize(
    ("label", "expected"),
    [
        # Phase 3 ML labels
        ("Food & Dining", "food_dining"),
        ("Utilities & Services", "utilities"),
        ("Healthcare & Medical", "health_insurance"),
        ("Shopping & Retail", "shopping_personal"),
        ("Entertainment & Recreation", "entertainment"),
        ("Transportation", "transportation"),
        ("Charity & Donations", "other"),
        ("Uncategorized", "other"),
        # Free text, ids and display names
        ("Groceries", "groceries"),
        ("rent", "housing"),
        ("Utilities", "utilities"),
        ("Food", "food_dining"),
        ("Home Loan EMI", "housing"),
        ("Car EMI", "emi_debt"),
        ("SIP", "savings_investments"),
        ("travel", "travel"),
        ("food_dining", "food_dining"),
        ("Housing & Rent", "housing"),
        ("Something Unknown", "other"),
        ("", "other"),
        (None, "other"),
        # An expense never becomes "income"
        ("Income", "other"),
        ("Salary", "other"),
    ],
)
def test_map_legacy_category(label, expected) -> None:
    assert map_legacy_category(label) == expected


def test_income_records_always_map_to_income() -> None:
    assert map_legacy_category("Salary", "income") == "income"
    assert map_legacy_category("Groceries", "income") == "income"


def test_every_current_id_and_name_maps_to_itself() -> None:
    for c in CATEGORIES:
        assert map_legacy_category(c.id) == c.id
        assert map_legacy_category(c.name) == c.id


async def test_migration_rewrites_old_records_idempotently(mongo_test_db) -> None:
    now = datetime.now(UTC)
    base = {"user_id": "u1", "amount": 100, "description": "x", "date": now, "created_at": now}
    await get_expenses_collection().insert_many(
        [
            {**base, "category": "Food & Dining", "category_source": "ml", "category_confidence": 0.9, "expense_type": "expense"},
            {**base, "category": "Salary", "category_source": "user", "expense_type": "income"},
            {**base, "category": "groceries", "expense_type": "expense"},
        ]
    )

    assert await migrate_expense_categories() == 2
    assert await migrate_expense_categories() == 0  # idempotent

    docs = await get_expenses_collection().find({}, {"_id": 0}).to_list(length=10)
    by_type = sorted((d["expense_type"], d["category"], d.get("legacy_category")) for d in docs)
    assert by_type == [
        ("expense", "food_dining", "Food & Dining"),
        ("expense", "groceries", None),
        ("income", "income", "Salary"),
    ]
    assert all("category_source" not in d and "category_confidence" not in d for d in docs)
