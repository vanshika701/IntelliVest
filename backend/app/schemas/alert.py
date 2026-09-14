"""Pydantic schemas for price proximity alerts."""

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class AlertCondition(str, Enum):
    above = "above"
    below = "below"
    within_pct = "within_pct"


class AlertCreate(BaseModel):
    ticker: str = Field(min_length=1, max_length=20)
    condition: AlertCondition
    target_price: float = Field(gt=0)
    # Only used when condition == "within_pct" — how close the current
    # price must be to the target to trigger (e.g. 5 means "within 5%").
    threshold_pct: float = Field(default=5.0, ge=0.1, le=50.0)


class AlertResponse(BaseModel):
    id: str
    user_id: str
    ticker: str
    condition: AlertCondition
    target_price: float
    threshold_pct: float
    is_active: bool
    triggered: bool
    triggered_at: datetime | None = None
    created_at: datetime
    latest_price: float | None = None
