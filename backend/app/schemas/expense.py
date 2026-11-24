"""Pydantic schemas for the expense / budgeting module."""

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field, model_validator

from app.core.budget_config import CATEGORIES, CATEGORY_BY_ID, INCOME_CATEGORY_ID

_NAME_TO_ID = {c.name.lower(): c.id for c in CATEGORIES}


class ExpenseType(str, Enum):
    income = "income"
    expense = "expense"


class ExpenseCreate(BaseModel):
    amount: float = Field(gt=0)
    description: str = Field(min_length=1, max_length=300)
    # Phase 8: picked by the user from the fixed list in core/budget_config.py
    # (id like "groceries", or its display name). Required for expenses;
    # income records always get "income". No auto-categorization.
    category: str | None = Field(default=None, max_length=60)
    expense_type: ExpenseType = ExpenseType.expense
    date: datetime | None = None  # defaults to now if omitted

    @model_validator(mode="after")
    def _resolve_category(self) -> "ExpenseCreate":
        if self.expense_type == ExpenseType.income:
            self.category = INCOME_CATEGORY_ID
            return self
        raw = (self.category or "").strip()
        resolved = raw if raw in CATEGORY_BY_ID else _NAME_TO_ID.get(raw.lower())
        if resolved is None:
            raise ValueError(
                "category is required for expenses and must be one of: "
                + ", ".join(c.id for c in CATEGORIES)
            )
        self.category = resolved
        return self


class ExpenseResponse(BaseModel):
    id: str
    user_id: str
    amount: float
    description: str
    category: str
    expense_type: ExpenseType
    date: datetime
    created_at: datetime


class ExpenseSummary(BaseModel):
    total_income: float
    total_expense: float
    net: float
    by_category: dict[str, float]


class CsvUploadResult(BaseModel):
    imported: int
    skipped: int
    errors: list[str]
