"""Pydantic schemas for the Phase 8 smart budgeter and goal planner."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.core.budget_config import CATEGORY_BY_ID, MAX_GOAL_HORIZON_MONTHS

Basis = Literal["auto", "actual", "estimated"]

_MAX_AMOUNT = 1e10  # ₹1,000 crore: catches typos, not a real-world limit


class BudgetProfileIn(BaseModel):
    monthly_income: float = Field(ge=0, le=_MAX_AMOUNT)
    # Monthly estimate per category id. Missing categories count as 0.
    estimates: dict[str, float] = Field(default_factory=dict)
    # Money already set aside for emergencies (optional).
    emergency_fund: float | None = Field(default=None, ge=0, le=_MAX_AMOUNT)

    @field_validator("estimates")
    @classmethod
    def _check_estimates(cls, value: dict[str, float]) -> dict[str, float]:
        unknown = sorted(set(value) - set(CATEGORY_BY_ID))
        if unknown:
            raise ValueError(f"Unknown categories: {', '.join(unknown)}")
        for key, amount in value.items():
            if amount is None or amount < 0 or amount > _MAX_AMOUNT:
                raise ValueError(f"Estimate for {key} must be a non-negative amount")
        return value


class BudgetProfileOut(BudgetProfileIn):
    user_id: str
    updated_at: datetime


class GoalIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    target_amount: float = Field(gt=0, le=_MAX_AMOUNT)
    horizon_months: int = Field(ge=1, le=MAX_GOAL_HORIZON_MONTHS)
    # None = use the default for the horizon (see budget_config.RETURN_ASSUMPTIONS).
    annual_return_pct: float | None = Field(default=None, ge=0, le=30)
    step_up_pct: float | None = Field(default=None, ge=0, le=50)


class ExplainIn(BaseModel):
    kind: Literal["improve", "goal"]
    focus: str | None = None  # category id or "all" (kind=improve)
    goal_id: str | None = None  # kind=goal
    basis: Basis = "auto"
