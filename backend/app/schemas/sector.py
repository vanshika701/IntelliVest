"""Pydantic schemas for Phase 6 sector intelligence."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel

Trend = Literal["up", "down", "flat"]
Label = Literal["positive", "negative", "neutral"]


class SectorSentiment(BaseModel):
    score: float | None
    label: Label | None  # None when there are too few articles
    article_count: int
    label_counts: dict[str, int]
    window_days: int


class SectorStock(BaseModel):
    ticker: str
    name: str
    price: float | None
    changes: dict[str, float | None]  # keys: 1d, 1w, 1m, 3m
    sentiment_score: float | None
    sentiment_label: Label | None
    article_count: int


class SeriesPoint(BaseModel):
    t: str
    v: float


class Sector(BaseModel):
    sector: str
    name: str
    stock_count: int
    priced_count: int
    as_of: datetime | None
    changes: dict[str, float | None]
    trend: Trend | None
    advancers: int
    decliners: int
    sentiment: SectorSentiment
    series: list[SeriesPoint]
    stocks: list[SectorStock]
    computed_at: datetime
