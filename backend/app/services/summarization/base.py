"""The Summarizer interface every implementation (extractive baseline,
future trained model) must satisfy. The rest of the app only sees this
module and `factory.get_summarizer()`.
"""

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass

logger = logging.getLogger(__name__)

DEFAULT_MAX_WORDS = 100


@dataclass(frozen=True)
class SummaryInput:
    title: str
    text: str
    max_words: int = DEFAULT_MAX_WORDS
    url: str | None = None
    # Lets an implementation favour sentences about the instrument.
    instrument_name: str | None = None


@dataclass(frozen=True)
class SummaryResult:
    summary: str
    word_count: int
    provider: str  # e.g. "extractive", "ml"
    method: str  # e.g. "tfidf-extractive@1.0.0", "bart-finetuned@2026-12"
    latency_ms: float


@dataclass(frozen=True)
class SummaryFailure:
    """One item in a batch that failed; the others are unaffected."""

    error: str
    provider: str
    url: str | None = None


class Summarizer(ABC):
    """Contract: `summary` is plain text and `word_count <= max_words`, always."""

    provider: str
    method: str

    @abstractmethod
    def summarize(self, item: SummaryInput) -> SummaryResult: ...

    def summarize_batch(self, items: list[SummaryInput]) -> list[SummaryResult | SummaryFailure]:
        """Summarize each item independently: one failure becomes a
        SummaryFailure in its slot instead of failing the whole batch."""
        results: list[SummaryResult | SummaryFailure] = []
        for item in items:
            try:
                results.append(self.summarize(item))
            except Exception as exc:  # noqa: BLE001 — isolation is the point
                logger.warning("Summarizer %s failed for %s: %s", self.provider, item.url or item.title[:60], exc)
                results.append(SummaryFailure(error=str(exc) or type(exc).__name__, provider=self.provider, url=item.url))
        return results

    def cache_fingerprint(self) -> str:
        """Changes whenever output could change (algorithm, config, model
        version) — part of the summary cache key."""
        return self.method
