"""Pydantic schemas for the expense / budgeting module."""

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class ExpenseType(str, Enum):
    income = "income"
    expense = "expense"


class ExpenseCreate(BaseModel):
    amount: float = Field(gt=0)
    description: str = Field(min_length=1, max_length=300)
    # Optional as of Phase 3: omit it and the ML categorizer predicts one
    # from the description instead of requiring the user to pick.
    category: str | None = Field(default=None, min_length=1, max_length=60)
    expense_type: ExpenseType = ExpenseType.expense
    date: datetime | None = None  # defaults to now if omitted


class ExpenseResponse(BaseModel):
    id: str
    user_id: str
    amount: float
    description: str
    category: str
    expense_type: ExpenseType
    date: datetime
    created_at: datetime
    # Phase 3: was this category typed by the user, or predicted by the
    # ML model? Lets the UI show "auto-categorized" transparently rather
    # than presenting a guess as a fact. Defaulted for pre-Phase-3 records.
    category_source: str = "user"
    category_confidence: float | None = None


class ExpenseSummary(BaseModel):
    total_income: float
    total_expense: float
    net: float
    by_category: dict[str, float]


class CsvUploadResult(BaseModel):
    imported: int
    skipped: int
    errors: list[str]
