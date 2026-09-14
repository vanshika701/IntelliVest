"""Pydantic schemas for the smart watchlist module."""

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class Priority(str, Enum):
    high = "high"
    medium = "medium"
    low = "low"


class WatchlistItemCreate(BaseModel):
    ticker: str = Field(min_length=1, max_length=20)
    notes: str = Field(default="", max_length=500)
    rationale: str = Field(default="", max_length=1000)
    priority: Priority = Priority.medium


class WatchlistItemUpdate(BaseModel):
    notes: str | None = Field(default=None, max_length=500)
    rationale: str | None = Field(default=None, max_length=1000)
    priority: Priority | None = None


class WatchlistItemResponse(BaseModel):
    id: str
    user_id: str
    ticker: str
    notes: str
    rationale: str
    priority: Priority
    added_at: datetime
    # Enriched from prices collection at read-time — may be None if no
    # price data has been ingested for this ticker yet.
    latest_price: float | None = None
    previous_close: float | None = None
    change_pct: float | None = None
