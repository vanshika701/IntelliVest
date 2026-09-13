"""Shared result type for ingestion services.

Market data, news, and (soon) Reddit ingestion all report success/failure
per source the same way — one shape here means the runner scripts can
summarize any of them identically instead of each inventing its own.
"""

from dataclasses import dataclass


@dataclass
class TickerIngestResult:
    ticker: str
    records_upserted: int
    error: str | None = None
