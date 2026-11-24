"""Map old/free-text expense categories onto the fixed Phase 8 list.

Before Phase 8, `category` was free text typed by the user or a label from
the (now removed) Phase 3 ML categorizer. This maps those *labels*
deterministically onto the new category ids. It never looks at the
transaction description, so it isn't a categorizer in disguise. Anything
it can't place goes to "Other / Miscellaneous" for the user to re-pick.

Also used by CSV import, so a statement's "Category" column like
"Groceries" or "Rent" lands on the right id.
"""

import logging
import re

from app.core.budget_config import (
    CATEGORIES,
    CATEGORY_BY_ID,
    FALLBACK_CATEGORY_ID,
    INCOME_CATEGORY_ID,
)
from app.data.collections import get_expenses_collection

logger = logging.getLogger(__name__)

# Exact labels (lower-cased) -> category id. Includes the 10 labels the
# Phase 3 model produced and the common free-text labels seen in the app.
LEGACY_LABELS: dict[str, str] = {
    # Phase 3 ML labels
    "charity & donations": "other",
    "entertainment & recreation": "entertainment",
    "financial services": "other",
    "food & dining": "food_dining",
    "government & legal": "other",
    "healthcare & medical": "health_insurance",
    "income": INCOME_CATEGORY_ID,
    "shopping & retail": "shopping_personal",
    "transportation": "transportation",
    "utilities & services": "utilities",
    # Old fallbacks
    "uncategorized": "other",
    "imported": "other",
    # Common free text
    "salary": INCOME_CATEGORY_ID,
    "freelance": INCOME_CATEGORY_ID,
}

# Keyword fallbacks on the label (first match wins, whole-word, case-insensitive).
_KEYWORD_RULES: list[tuple[str, str]] = [
    (r"rent|housing|home loan|mortgage|maintenance", "housing"),
    (r"grocer\w*|supermarket|kirana", "groceries"),
    (r"food|dining|restaurant|cafe|coffee|swiggy|zomato|eat\w*", "food_dining"),
    (r"transport\w*|fuel|petrol|diesel|cab|uber|ola|metro|commute|auto", "transportation"),
    (r"utilit\w*|bill\w*|electricity|water|gas|internet|broadband|mobile|phone|recharge", "utilities"),
    (r"health\w*|medical|medicine|doctor|hospital|pharmacy|insurance|fitness|gym", "health_insurance"),
    (r"shopping|clothes|clothing|apparel|personal care|salon|grooming|retail", "shopping_personal"),
    (r"entertainment|leisure|movie\w*|subscription\w*|ott|netflix|games?|recreation", "entertainment"),
    (r"travel|flight\w*|hotel\w*|trip|vacation|holiday", "travel"),
    (r"education|tuition|course\w*|school|college|books?", "education"),
    (r"emi|loan|debt|credit card", "emi_debt"),
    (r"saving\w*|invest\w*|sip|mutual fund|stocks?|fd|rd|ppf|nps", "savings_investments"),
    (r"income|salary|wages|bonus|refund", INCOME_CATEGORY_ID),
]

_VALID_IDS = {c.id for c in CATEGORIES}
_NAME_TO_ID = {c.name.lower(): c.id for c in CATEGORIES}


def map_legacy_category(label: str | None, expense_type: str = "expense") -> str:
    """Return the Phase 8 category id for an old label.

    Income records always map to "income"; an expense never maps to
    "income" (a label like "Refund" on an expense goes to Other).
    """
    if expense_type == "income":
        return INCOME_CATEGORY_ID
    if not label or not label.strip():
        return FALLBACK_CATEGORY_ID

    raw = label.strip()
    lowered = raw.lower()
    if lowered in _VALID_IDS:
        mapped = lowered
    elif lowered in _NAME_TO_ID:
        mapped = _NAME_TO_ID[lowered]
    elif lowered in LEGACY_LABELS:
        mapped = LEGACY_LABELS[lowered]
    else:
        mapped = FALLBACK_CATEGORY_ID
        for pattern, cat_id in _KEYWORD_RULES:
            if re.search(rf"\b(?:{pattern})\b", lowered):
                mapped = cat_id
                break

    return FALLBACK_CATEGORY_ID if mapped == INCOME_CATEGORY_ID else mapped


def is_valid_spending_category(category_id: str) -> bool:
    return category_id in CATEGORY_BY_ID


async def migrate_expense_categories() -> int:
    """Rewrite every expense whose category isn't a current id. Idempotent:
    already-migrated records are skipped, so it's safe on every startup.
    The original label is kept in `legacy_category` and the removed ML
    fields (`category_source`, `category_confidence`) are dropped.
    Returns the number of records changed."""
    collection = get_expenses_collection()
    valid = sorted(_VALID_IDS | {INCOME_CATEGORY_ID})
    query = {
        "$or": [
            {"category": {"$nin": valid}},
            {"category_source": {"$exists": True}},
            # Income must be "income"; expenses must not be.
            {"expense_type": "income", "category": {"$ne": INCOME_CATEGORY_ID}},
            {"expense_type": {"$ne": "income"}, "category": INCOME_CATEGORY_ID},
        ]
    }
    changed = 0
    async for doc in collection.find(query, {"category": 1, "expense_type": 1}):
        old = doc.get("category")
        new = map_legacy_category(old, doc.get("expense_type", "expense"))
        update: dict = {
            "$set": {"category": new},
            "$unset": {"category_source": "", "category_confidence": ""},
        }
        if old != new:
            update["$set"]["legacy_category"] = old
        await collection.update_one({"_id": doc["_id"]}, update)
        changed += 1
    if changed:
        logger.info("Migrated %d expense records to Phase 8 categories", changed)
    return changed
