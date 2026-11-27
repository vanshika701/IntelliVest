"""Sentiment evidence from stored FinBERT scores (Phase 10, B13)."""

from datetime import UTC, datetime, timedelta

import pytest

from app.core.config import settings
from app.services.blockchain import hashing
from app.services.blockchain.formats import EvidenceStatus, Step
from app.services.blockchain.sentiment_evidence import build_sentiment_evidence

TASK = b"\x01" * 32
NOW = datetime(2026, 11, 27, 12, tzinfo=UTC)


def _article(score: float, days_ago: float = 1, model: str | None = None, **over) -> dict:
    return {
        "url": f"https://news.example/{score}-{days_ago}",
        "title": f"Headline {score}",
        "published_at": NOW - timedelta(days=days_ago),
        "sentiment": {
            "label": "x",
            "score": score,
            "model": model or settings.sentiment_model,
            "revision": "abc123",
        },
    } | over


def test_finbert_scores_give_ok_evidence():
    articles = [_article(0.5), _article(0.2), _article(-0.1)]
    result = build_sentiment_evidence(TASK, "RELIANCE", articles, NOW, "1")
    e = result.evidence
    assert (e.step, e.status, e.score, e.count) == (Step.SENTIMENT, EvidenceStatus.OK, 2000, 3)
    assert e.modelId == hashing.model_id(
        settings.sentiment_model
    ) and e.modelVersion == hashing.model_id("1")
    assert e.asOf == int(NOW.timestamp())
    assert result.outputs["article_scores_bps"] == [5000, 2000, -1000]
    assert result.inputs["revisions"] == ["abc123"] and result.inputs["engines"] == [
        settings.sentiment_model
    ]
    assert e.inputHash == hashing.hash_data(result.inputs) and e.outputHash == hashing.hash_data(
        result.outputs
    )


def test_article_text_stays_off_chain():
    result = build_sentiment_evidence(TASK, "X", [_article(0.1)] * 3, NOW, "1")
    entry = result.inputs["articles"][0]
    assert (
        set(entry) == {"url", "text_hash"}
        and entry["text_hash"] == "0x" + hashing.hash_text("Headline 0.1").hex()
    )


def test_too_few_articles_is_no_data():
    e = build_sentiment_evidence(TASK, "X", [_article(0.9), _article(0.9)], NOW, "1").evidence
    assert (e.status, e.score, e.count) == (EvidenceStatus.NO_DATA, 0, 2)


def test_old_articles_are_outside_the_window():
    articles = [_article(0.5), _article(0.5), _article(0.5, days_ago=8)]
    assert (
        build_sentiment_evidence(TASK, "X", articles, NOW, "1").evidence.status
        == EvidenceStatus.NO_DATA
    )


@pytest.mark.parametrize("model", ["lexicon", "someone/other-model"])
def test_non_finbert_scores_are_fallback_never_ok(model):
    articles = [_article(0.5), _article(0.5), _article(0.5, model=model)]
    e = build_sentiment_evidence(TASK, "X", articles, NOW, "1").evidence
    assert e.status == EvidenceStatus.FALLBACK and e.score == 5000


def test_score_is_clamped_and_naive_dates_are_utc():
    naive = NOW.replace(tzinfo=None) - timedelta(days=1)
    articles = [_article(1.0, published_at=naive)] * 3
    assert build_sentiment_evidence(TASK, "X", articles, NOW, "1").evidence.score == 10_000


def test_no_ticker_is_no_data():
    e = build_sentiment_evidence(TASK, "", [], NOW, "1").evidence
    assert e.status == EvidenceStatus.NO_DATA and e.count == 0
