"""Pydantic schemas for the Phase 5 news sentiment view."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel

SentimentLabel = Literal["positive", "negative", "neutral"]


class SentimentArticle(BaseModel):
    title: str
    url: str
    source: str | None = None
    published_at: datetime
    label: SentimentLabel
    # Positive minus negative probability, from -1 (very negative) to 1.
    score: float


class TickerSentimentSummary(BaseModel):
    ticker: str
    window_days: int
    article_count: int
    label_counts: dict[SentimentLabel, int]
    # None when no scored articles fall inside the window yet.
    average_score: float | None = None
    overall_label: SentimentLabel | None = None
    recent_articles: list[SentimentArticle]
