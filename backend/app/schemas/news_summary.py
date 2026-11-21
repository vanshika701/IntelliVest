"""Pydantic schemas for per-article news summaries."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel

# What the summary was built from: the publisher's full article, the RSS
# description snippet, or only the headline.
InputKind = Literal["full_text", "snippet", "headline"]


class NewsSummaryItem(BaseModel):
    title: str
    url: str
    source: str | None = None
    published_at: datetime
    summary: str
    word_count: int
    input_kind: InputKind
    # True when the full article couldn't be used (snippet or headline only).
    used_fallback: bool
    # True when the summarizer itself failed for this item; summary is then the headline.
    summary_failed: bool = False


class NewsSummaries(BaseModel):
    instrument_id: str
    provider: str
    method: str
    max_words: int
    items: list[NewsSummaryItem]
    generated_at: datetime
