"""Service layer for expense / budgeting features.

Handles CSV statement parsing and delegates storage to the repository.
"""

import csv
import io
import logging
from datetime import UTC, datetime

from app.data.expense_repository import (
    count_expenses_for_user,
    delete_expense,
    get_expense_summary,
    get_expenses_for_user,
    insert_expense,
    insert_many_expenses,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Manual expense entry
# ---------------------------------------------------------------------------

async def add_expense(user_id: str, data: dict) -> str:
    """Validate and store a single expense. Returns the new expense ID."""
    if data.get("date") is None:
        data["date"] = datetime.now(UTC)
    return await insert_expense(user_id, data)


async def list_expenses(user_id: str, skip: int = 0, limit: int = 50) -> dict:
    """Return paginated expenses plus total count."""
    items = await get_expenses_for_user(user_id, skip=skip, limit=limit)
    total = await count_expenses_for_user(user_id)
    # Convert ObjectId to string for JSON serialization
    for item in items:
        item["id"] = str(item.pop("_id"))
    return {"items": items, "total": total, "skip": skip, "limit": limit}


async def remove_expense(user_id: str, expense_id: str) -> bool:
    return await delete_expense(user_id, expense_id)


async def summarize_expenses(user_id: str) -> dict:
    return await get_expense_summary(user_id)


# ---------------------------------------------------------------------------
# CSV statement upload
# ---------------------------------------------------------------------------

# Column name synonyms the parser recognizes (case-insensitive).
_DATE_COLS = {"date", "transaction date", "txn date", "value date"}
_DESC_COLS = {"description", "narration", "particulars", "remarks", "memo"}
_AMOUNT_COLS = {"amount", "transaction amount", "txn amount"}
_DEBIT_COLS = {"debit", "withdrawal", "withdrawals"}
_CREDIT_COLS = {"credit", "deposit", "deposits"}
_CATEGORY_COLS = {"category", "type", "expense type"}


def _find_col(headers: list[str], synonyms: set[str]) -> int | None:
    """Return the index of the first header matching any synonym."""
    for i, h in enumerate(headers):
        if h.strip().lower() in synonyms:
            return i
    return None


def _parse_date(raw: str) -> datetime | None:
    """Best-effort date parsing for common CSV date formats."""
    for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%m/%d/%Y", "%d/%m/%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(raw.strip(), fmt).replace(tzinfo=UTC)
        except ValueError:
            continue
    return None


def _parse_amount(raw: str) -> float | None:
    """Parse a monetary amount, stripping currency symbols and commas."""
    cleaned = raw.strip().replace(",", "").replace("₹", "").replace("$", "").replace("Rs", "")
    try:
        return abs(float(cleaned))
    except ValueError:
        return None


async def import_csv(user_id: str, file_bytes: bytes) -> dict:
    """Parse a CSV statement and bulk-insert valid rows.

    Returns a summary dict with imported/skipped counts and per-row errors.
    """
    text = file_bytes.decode("utf-8-sig")  # BOM-safe
    reader = csv.reader(io.StringIO(text))

    try:
        headers = next(reader)
    except StopIteration:
        return {"imported": 0, "skipped": 0, "errors": ["CSV file is empty"]}

    date_idx = _find_col(headers, _DATE_COLS)
    desc_idx = _find_col(headers, _DESC_COLS)
    amount_idx = _find_col(headers, _AMOUNT_COLS)
    debit_idx = _find_col(headers, _DEBIT_COLS)
    credit_idx = _find_col(headers, _CREDIT_COLS)
    category_idx = _find_col(headers, _CATEGORY_COLS)

    if date_idx is None:
        return {"imported": 0, "skipped": 0, "errors": ["No date column found"]}
    if amount_idx is None and debit_idx is None and credit_idx is None:
        return {"imported": 0, "skipped": 0, "errors": ["No amount/debit/credit column found"]}

    now = datetime.now(UTC)
    records: list[dict] = []
    errors: list[str] = []
    skipped = 0

    for row_num, row in enumerate(reader, start=2):
        if not any(cell.strip() for cell in row):
            skipped += 1
            continue

        # Date
        date = _parse_date(row[date_idx]) if date_idx < len(row) else None
        if date is None:
            errors.append(f"Row {row_num}: could not parse date '{row[date_idx] if date_idx < len(row) else ''}'")
            skipped += 1
            continue

        # Description
        description = row[desc_idx].strip() if desc_idx is not None and desc_idx < len(row) else "Imported"

        # Amount & type
        if amount_idx is not None and amount_idx < len(row):
            amount = _parse_amount(row[amount_idx])
            expense_type = "expense"  # Will be overridden if category column says otherwise
        elif debit_idx is not None and debit_idx < len(row) and row[debit_idx].strip():
            amount = _parse_amount(row[debit_idx])
            expense_type = "expense"
        elif credit_idx is not None and credit_idx < len(row) and row[credit_idx].strip():
            amount = _parse_amount(row[credit_idx])
            expense_type = "income"
        else:
            errors.append(f"Row {row_num}: no amount value found")
            skipped += 1
            continue

        if amount is None or amount <= 0:
            errors.append(f"Row {row_num}: invalid amount")
            skipped += 1
            continue

        # Category (optional)
        category = "Uncategorized"
        if category_idx is not None and category_idx < len(row):
            cat = row[category_idx].strip()
            if cat:
                category = cat

        records.append(
            {
                "user_id": user_id,
                "amount": amount,
                "description": description,
                "category": category,
                "expense_type": expense_type,
                "date": date,
                "created_at": now,
            }
        )

    imported = await insert_many_expenses(records)
    logger.info(
        "CSV import for user %s: %d imported, %d skipped, %d errors",
        user_id, imported, skipped, len(errors),
    )
    return {"imported": imported, "skipped": skipped, "errors": errors}
