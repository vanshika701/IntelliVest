"""Sentiment service tests. The real FinBERT model is never loaded here —
classification is replaced with a fake, so these test our scoring and
aggregation logic, not the model itself."""

from datetime import UTC, datetime, timedelta

import pytest

from app.core.config import settings
from app.data.collections import get_news_collection
from app.services import sentiment_service
from app.services.sentiment_service import (
    article_text,
    overall_label,
    score_pending_articles,
    sentiment_from_probabilities,
    summarize_ticker_sentiment,
)


def test_sentiment_from_probabilities_picks_label_and_signed_score() -> None:
    result = sentiment_from_probabilities({"positive": 0.1, "negative": 0.7, "neutral": 0.2})
    assert result["label"] == "negative"
    assert result["score"] == pytest.approx(-0.6)


def test_article_text_joins_title_and_optional_description() -> None:
    assert article_text({"title": "Infosys wins deal", "description": "Large contract."}) == (
        "Infosys wins deal. Large contract."
    )
    assert article_text({"title": "Infosys wins deal", "description": None}) == "Infosys wins deal"


def test_overall_label_uses_neutral_band() -> None:
    assert overall_label(0.5) == "positive"
    assert overall_label(-0.5) == "negative"
    assert overall_label(0.05) == "neutral"
    assert overall_label(None) is None


def _fake_classify(texts: list[str], model: str | None = None) -> list[dict[str, float]]:
    return [
        {"positive": 0.9, "negative": 0.05, "neutral": 0.05}
        if "beats" in t
        else {"positive": 0.05, "negative": 0.9, "neutral": 0.05}
        for t in texts
    ]


async def test_score_pending_articles_scores_once_and_rescores_on_model_change(
    mongo_test_db, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(sentiment_service, "_load_model", lambda *_: True)
    monkeypatch.setattr(sentiment_service, "classify", _fake_classify)
    monkeypatch.setattr(settings, "sentiment_extra_models", "")
    now = datetime.now(UTC)
    await get_news_collection().insert_many(
        [
            {"url": "u1", "title": "TCS beats estimates", "published_at": now, "tickers": ["TCS.NS"]},
            {"url": "u2", "title": "TCS misses estimates", "published_at": now, "tickers": ["TCS.NS"]},
        ]
    )

    assert await score_pending_articles() == 2
    stored = await get_news_collection().find_one({"url": "u1"})
    assert stored["sentiment"]["label"] == "positive"
    assert stored["sentiment"]["model"] == settings.sentiment_model

    # Already scored by this model: nothing to do on the next run.
    assert await score_pending_articles() == 0

    # Swapping in a different (e.g. fine-tuned) model re-scores everything.
    monkeypatch.setattr(settings, "sentiment_model", "local/finetuned-finbert")
    assert await score_pending_articles() == 2


async def test_extra_models_score_into_their_own_field(mongo_test_db, monkeypatch: pytest.MonkeyPatch) -> None:
    """The default model keeps writing `sentiment` (what other modules read);
    an extra model writes `sentiments.<key>`, and each is read back by name."""
    calls = []

    def fake_classify(texts: list[str], model: str | None = None) -> list[dict[str, float]]:
        calls.append(model)
        neutral = {"positive": 0.1, "negative": 0.1, "neutral": 0.8}
        return _fake_classify(texts) if model == "default/model" else [neutral for _ in texts]

    monkeypatch.setattr(sentiment_service, "_load_model", lambda *_: True)
    monkeypatch.setattr(sentiment_service, "classify", fake_classify)
    monkeypatch.setattr(settings, "sentiment_model", "default/model")
    monkeypatch.setattr(settings, "sentiment_extra_models", "other/model-v1.0")
    now = datetime.now(UTC)
    await get_news_collection().insert_one(
        {"url": "u1", "title": "TCS beats estimates", "published_at": now, "tickers": ["TCS.NS"]}
    )

    assert await score_pending_articles() == 2  # one article, two models
    assert calls == ["default/model", "other/model-v1.0"]
    stored = await get_news_collection().find_one({"url": "u1"})
    assert stored["sentiment"]["label"] == "positive"
    assert stored["sentiments"]["other_model_v1_0"]["label"] == "neutral"
    assert await score_pending_articles() == 0

    sentiment_service._instrument_sentiment_cache.clear()
    default = await sentiment_service.get_instrument_sentiment("stock-TCS.NS")
    other = await sentiment_service.get_instrument_sentiment("stock-TCS.NS", "other/model-v1.0")
    assert (default["model"], default["articles"][0]["label"]) == ("default/model", "positive")
    assert (other["model"], other["articles"][0]["label"]) == ("other/model-v1.0", "neutral")
    with pytest.raises(sentiment_service.UnknownSentimentModel):
        await sentiment_service.get_instrument_sentiment("stock-TCS.NS", "not/offered")


async def test_score_pending_articles_skips_run_when_model_unavailable(
    mongo_test_db, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(sentiment_service, "_load_model", lambda *_: False)
    await get_news_collection().insert_one(
        {"url": "u1", "title": "TCS beats", "published_at": datetime.now(UTC), "tickers": ["TCS.NS"]}
    )
    assert await score_pending_articles() == 0


async def test_summarize_ticker_sentiment_aggregates_window(mongo_test_db) -> None:
    now = datetime.now(UTC)

    def article(url: str, label: str, score: float, age_days: int, tickers=("INFY.NS",)) -> dict:
        return {
            "url": url,
            "title": url,
            "source": "Livemint",
            "published_at": now - timedelta(days=age_days),
            "tickers": list(tickers),
            "sentiment": {"label": label, "score": score, "model": "m"},
        }

    await get_news_collection().insert_many(
        [
            article("new-pos", "positive", 0.8, 0),
            article("mid-pos", "positive", 0.6, 1),
            article("mid-neg", "negative", -0.2, 2),
            article("too-old", "negative", -0.9, 30),
            article("other-ticker", "negative", -0.9, 0, tickers=("TCS.NS",)),
            {"url": "unscored", "title": "x", "published_at": now, "tickers": ["INFY.NS"]},
        ]
    )

    summary = await summarize_ticker_sentiment("INFY.NS", days=7, top_n=2)

    assert summary["article_count"] == 3
    assert summary["label_counts"] == {"positive": 2, "negative": 1, "neutral": 0}
    assert summary["average_score"] == pytest.approx(0.4)
    assert summary["overall_label"] == "positive"
    assert [a["url"] for a in summary["recent_articles"]] == ["new-pos", "mid-pos"]


async def test_summarize_ticker_sentiment_with_no_scored_articles(mongo_test_db) -> None:
    summary = await summarize_ticker_sentiment("ITC.NS")
    assert summary["article_count"] == 0
    assert summary["average_score"] is None
    assert summary["overall_label"] is None
    assert summary["recent_articles"] == []
