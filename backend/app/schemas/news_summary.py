"""Pydantic schemas for the combined news summary (news digest)."""

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel

from app.schemas.sentiment import SentimentLabel

# What an article contributed: the publisher's full text, the RSS
# description snippet, or only the headline.
InputKind = Literal["full_text", "snippet", "headline"]


class DigestArticle(BaseModel):
    title: str
    url: str
    source: str | None = None
    published_at: datetime
    input_kind: InputKind
    label: SentimentLabel
    score: float


class PriceMove(BaseModel):
    """The instrument's own price change, from our data rather than the news."""

    as_of: date
    day_pct: float | None = None
    week_pct: float | None = None
    month_pct: float | None = None
    text: str


class NewsDigest(BaseModel):
    instrument_id: str
    # "sector": too little news about the instrument, so its sector's or
    # theme's news is used; scope_name says which.
    scope: Literal["instrument", "sector"] = "instrument"
    scope_name: str
    price_move: PriceMove | None = None
    provider: str
    method: str
    # Summarizer key (see GET /models), e.g. "extractive".
    summarizer: str
    max_words: int
    # One summary of the top articles; None when there's no news or the
    # summarizer failed (see summary_failed).
    summary: str | None = None
    word_count: int
    summary_failed: bool = False
    # How many of the articles contributed full text / a snippet / a headline.
    sources: dict[InputKind, int]
    sentiment_engine: str | None = None
    articles: list[DigestArticle]
    generated_at: datetime
