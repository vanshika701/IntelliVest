"""The only place that knows about concrete summarizer implementations."""

from functools import lru_cache

from app.core.config import settings
from app.services.summarization.base import Summarizer
from app.services.summarization.extractive import ExtractiveSummarizer
from app.services.summarization.ml import MlSummarizer

PROVIDERS = ("extractive", "ml")


@lru_cache(maxsize=len(PROVIDERS))
def _build(provider: str) -> Summarizer:
    if provider == "extractive":
        return ExtractiveSummarizer()
    if provider == "ml":
        return MlSummarizer(settings.ml_summarizer_url)
    raise ValueError(f"Unknown SUMMARIZER_PROVIDER {provider!r}; expected one of {', '.join(PROVIDERS)}")


def get_summarizer(provider: str | None = None) -> Summarizer:
    """The summarizer selected by SUMMARIZER_PROVIDER (default: extractive)."""
    return _build((provider or settings.summarizer_provider).strip().lower())
