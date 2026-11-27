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


class InstrumentSentiment(BaseModel):
    instrument_id: str
    # None = not enough news to determine sentiment (see min_articles).
    label: SentimentLabel | None = None
    average_score: float | None = None
    article_count: int
    min_articles: int
    window_days: int
    # Which engine scored the headlines, e.g. "ProsusAI/finbert" or "lexicon".
    engine: str
    # The sentiment model asked for (the default unless one was picked).
    model: str
    model_label: str
    articles: list[SentimentArticle]
    generated_at: datetime


class TickerSentimentSummary(BaseModel):
    ticker: str
    window_days: int
    article_count: int
    label_counts: dict[SentimentLabel, int]
    # None when no scored articles fall inside the window yet.
    average_score: float | None = None
    overall_label: SentimentLabel | None = None
    recent_articles: list[SentimentArticle]
