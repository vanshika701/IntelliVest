"""News summarization. Import the interface and `get_summarizer` from here;
concrete implementations are chosen by the factory, never imported directly."""

from app.services.summarization.base import (
    DEFAULT_MAX_WORDS,
    Summarizer,
    SummaryFailure,
    SummaryInput,
    SummaryResult,
)
from app.services.summarization.factory import get_summarizer

__all__ = [
    "DEFAULT_MAX_WORDS",
    "Summarizer",
    "SummaryFailure",
    "SummaryInput",
    "SummaryResult",
    "get_summarizer",
]
