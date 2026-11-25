"""Pydantic schemas for the expense / budgeting module."""

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field, model_validator

from app.core.budget_config import (
    CATEGORIES,
    CATEGORY_BY_ID,
    INCOME_CATEGORY_ID,
    INCOME_SOURCE_BY_ID,
)

_NAME_TO_ID = {c.name.lower(): c.id for c in CATEGORIES}


class ExpenseType(str, Enum):
    income = "income"
    expense = "expense"


def resolve_category(raw: str | None) -> str:
    """Category id from an id or display name; ValueError if not in the list."""
    value = (raw or "").strip()
    resolved = value if value in CATEGORY_BY_ID else _NAME_TO_ID.get(value.lower())
    if resolved is None:
        raise ValueError(
            "category is required for expenses and must be one of: " + ", ".join(c.id for c in CATEGORIES)
        )
    return resolved


def check_income_source(source: str | None) -> str:
    if source not in INCOME_SOURCE_BY_ID:
        raise ValueError(
            "income_source is required for income and must be one of: " + ", ".join(INCOME_SOURCE_BY_ID)
        )
    return source


class ExpenseCreate(BaseModel):
    amount: float = Field(gt=0)
    description: str = Field(min_length=1, max_length=300)
    # Phase 8: picked by the user from the fixed list in core/budget_config.py
    # (id like "groceries", or its display name). Required for expenses;
    # income records always get "income". No auto-categorization.
    category: str | None = Field(default=None, max_length=60)
    expense_type: ExpenseType = ExpenseType.expense
    # Where income came from (budget_config.INCOME_SOURCES). Required for
    # income, always empty for expenses.
    income_source: str | None = Field(default=None, max_length=60)
    date: datetime | None = None  # defaults to now if omitted

    @model_validator(mode="after")
    def _resolve_category(self) -> "ExpenseCreate":
        if self.expense_type == ExpenseType.income:
            self.category = INCOME_CATEGORY_ID
            check_income_source(self.income_source)
            return self
        self.category = resolve_category(self.category)
        self.income_source = None
        return self


class ExpenseUpdate(BaseModel):
    """Partial update. Whether a record is income or an expense can't change."""

    amount: float | None = Field(default=None, gt=0)
    description: str | None = Field(default=None, min_length=1, max_length=300)
    category: str | None = Field(default=None, max_length=60)
    income_source: str | None = Field(default=None, max_length=60)
    date: datetime | None = None


class ExpenseResponse(BaseModel):
    id: str
    user_id: str
    amount: float
    description: str
    category: str
    expense_type: ExpenseType
    income_source: str | None = None  # None on records older than this field
    date: datetime
    created_at: datetime


class ExpenseSummary(BaseModel):
    total_income: float
    total_expense: float
    net: float
    by_category: dict[str, float]
    # Income per source id; "unspecified" for records without one.
    by_income_source: dict[str, float] = {}


class CsvUploadResult(BaseModel):
    imported: int
    skipped: int
    errors: list[str]
