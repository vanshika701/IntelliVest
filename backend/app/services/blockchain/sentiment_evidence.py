"""Sentiment evidence from stored FinBERT scores (Phase 10, B13).

Reads articles Phase 5 already scored; it never runs the model. A fixed
7-day window keeps the evidence reproducible. The on-chain score is the
average (positive minus negative probability) in basis points.

- Fewer than MIN_ARTICLES articles: NO_DATA.
- Any article not scored by the configured FinBERT model (for example the
  `lexicon` fallback): FALLBACK, so it is never treated as FinBERT. The
  contract then asks the owner or rejects, as the mandate says.
"""

from datetime import UTC, datetime, timedelta

from app.core.config import settings
from app.services.blockchain import hashing
from app.services.blockchain.formats import BPS, Evidence, EvidenceResult, EvidenceStatus, Step

WINDOW_DAYS = 7
MIN_ARTICLES = 3  # same as the sentiment page's MIN_ARTICLES_FOR_LABEL


def build_sentiment_evidence(
    task_id: bytes,
    ticker: str,
    articles: list[dict],
    now: datetime,
    registered_version: str,
    model_name: str | None = None,
) -> EvidenceResult:
    """`articles`: stored news documents with a `sentiment` field, newest first."""
    model_name = model_name or settings.sentiment_model
    since = now - timedelta(days=WINDOW_DAYS)
    window = [a for a in articles if _utc(a["published_at"]) >= since and a.get("sentiment")]
    engines = sorted({a["sentiment"].get("model") or "unknown" for a in window})
    revisions = sorted({a["sentiment"].get("revision") or "unknown" for a in window})
    inputs = {
        "ticker": ticker,
        "window_days": WINDOW_DAYS,
        "until": now.date().isoformat(),
        "engines": engines,
        "revisions": revisions,
        "articles": [
            {
                "url": a.get("url", ""),
                "text_hash": "0x" + hashing.hash_text(a.get("title", "")).hex(),
            }
            for a in window
        ],
    }
    scores = [_bps(a["sentiment"]["score"]) for a in window]
    if len(window) < MIN_ARTICLES:
        status, score = EvidenceStatus.NO_DATA, 0
    else:
        score = max(-BPS, min(BPS, round(sum(scores) / len(scores))))
        status = EvidenceStatus.OK if engines == [model_name] else EvidenceStatus.FALLBACK
    outputs = {"score_bps": score, "article_scores_bps": scores, "status": status.name}
    evidence = Evidence(
        taskId=task_id,
        step=int(Step.SENTIMENT),
        status=int(status),
        modelId=hashing.model_id(model_name),
        modelVersion=hashing.model_id(registered_version),
        inputHash=hashing.hash_data(inputs),
        outputHash=hashing.hash_data(outputs),
        score=score,
        count=len(window),
        horizonDays=0,
        asOf=int(now.timestamp()),
    )
    return EvidenceResult(evidence, inputs, outputs)


async def sentiment_evidence(
    task_id: bytes, ticker: str, registered_version: str, now: datetime | None = None
) -> EvidenceResult:
    from app.data.news_repository import get_scored_articles_for_ticker

    now = now or datetime.now(UTC)
    articles = []
    if ticker:
        articles = await get_scored_articles_for_ticker(ticker, now - timedelta(days=WINDOW_DAYS))
    return build_sentiment_evidence(task_id, ticker, articles, now, registered_version)


def _utc(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def _bps(value: float) -> int:
    return round(value * BPS)
