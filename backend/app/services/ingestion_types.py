"""Shared result type for ingestion services.

Market data, news, and Reddit ingestion all report success/failure per
source the same way — one shape here means the runner scripts can
summarize any of them identically instead of each inventing its own.
`source` is deliberately generic: it's a ticker for market data/news, a
subreddit name for Reddit.
"""

from dataclasses import dataclass


@dataclass
class IngestResult:
    source: str
    records_upserted: int
    error: str | None = None
