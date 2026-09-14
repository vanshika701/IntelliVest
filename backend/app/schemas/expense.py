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
    category: str = Field(min_length=1, max_length=60)
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


class ExpenseSummary(BaseModel):
    total_income: float
    total_expense: float
    net: float
    by_category: dict[str, float]


class CsvUploadResult(BaseModel):
    imported: int
    skipped: int
    errors: list[str]
