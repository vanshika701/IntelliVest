"""Instrument-level sentiment tests. FinBERT, Google News and mfapi.in are
faked; these test aggregation, the "not enough news" rule, caching and
error handling."""

from datetime import UTC, datetime, timedelta

import httpx
import pytest
from fastapi.testclient import TestClient

from app.data.collections import get_news_collection
from app.services import sentiment_service
from app.services.sentiment_service import (
    fund_news_phrase,
    get_instrument_sentiment,
    lexicon_classify,
    score_texts,
)


@pytest.fixture(autouse=True)
def _fresh_cache():
    sentiment_service._instrument_sentiment_cache.clear()


@pytest.fixture
def fake_fund(monkeypatch: pytest.MonkeyPatch):
    async def fake_get_instrument(instrument_id: str) -> dict:
        return {"id": instrument_id, "name": "SBI GOLD FUND - Direct Plan - Growth", "type": "MF"}

    monkeypatch.setattr(sentiment_service, "get_instrument", fake_get_instrument)


def _news(n: int) -> list[dict]:
    now = datetime.now(UTC)
    return [
        {
            "url": f"https://news.example/{i}",
            "title": f"Gold prices surge to record high {i}" if i % 3 else f"Gold falls as demand slows {i}",
            "description": None,
            "source": "Mint",
            "published_at": now - timedelta(hours=i),
        }
        for i in range(n)
    ]


def test_fund_news_phrase_drops_plan_and_option() -> None:
    assert fund_news_phrase("SBI GOLD FUND - Direct Plan - Growth") == "SBI GOLD FUND"
    assert fund_news_phrase("Edelweiss Gold ETF") == "Edelweiss Gold ETF"


def test_lexicon_classify_scores_obvious_headlines() -> None:
    pos, neg, neutral = lexicon_classify(
        ["Gold surges to record high", "Fund outflows as markets slump", "Fund house appoints new CEO"]
    )
    assert max(pos, key=pos.get) == "positive"
    assert max(neg, key=neg.get) == "negative"
    assert max(neutral, key=neutral.get) == "neutral"


def test_score_texts_falls_back_to_lexicon_when_model_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sentiment_service, "_load_model", lambda: False)
    probabilities, engine = score_texts(["Gold surges"])
    assert engine == "lexicon"
    assert max(probabilities[0], key=probabilities[0].get) == "positive"


async def test_fund_sentiment_scores_fresh_news_and_is_cached(fake_fund, monkeypatch: pytest.MonkeyPatch) -> None:
    searches = []

    async def fake_search_news(phrase: str, days: int = 30, limit: int = 15) -> list[dict]:
        searches.append(phrase)
        return _news(6)

    monkeypatch.setattr(sentiment_service, "search_news", fake_search_news)
    monkeypatch.setattr(sentiment_service, "_load_model", lambda: False)

    first = await get_instrument_sentiment("mf-123")
    assert searches == ["SBI GOLD FUND"]
    assert first["engine"] == "lexicon"
    assert first["article_count"] == 6
    assert first["label"] == "positive"  # 4 "surge" vs 2 "falls"
    assert [a["label"] for a in first["articles"][:2]] == ["negative", "positive"]

    second = await get_instrument_sentiment("mf-123")
    assert second is first
    assert searches == ["SBI GOLD FUND"]


async def test_too_few_headlines_gives_no_label(fake_fund, monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_search_news(phrase: str, days: int = 30, limit: int = 15) -> list[dict]:
        return _news(2)

    monkeypatch.setattr(sentiment_service, "search_news", fake_search_news)
    monkeypatch.setattr(sentiment_service, "_load_model", lambda: False)

    result = await get_instrument_sentiment("mf-123")
    assert result["label"] is None
    assert result["average_score"] is None
    assert result["article_count"] == 2


async def test_stock_sentiment_uses_stored_scores_and_widens_window(mongo_test_db) -> None:
    now = datetime.now(UTC)
    await get_news_collection().insert_many(
        [
            {
                "url": f"u{i}",
                "title": f"t{i}",
                "source": "ET",
                "published_at": now - timedelta(days=age),
                "tickers": ["TCS.NS"],
                "sentiment": {"label": "negative", "score": -0.6, "model": "ProsusAI/finbert"},
            }
            for i, age in enumerate((1, 10, 20))
        ]
    )

    result = await get_instrument_sentiment("stock-TCS.NS")
    # Only one article in 7 days, so the window widens to 30.
    assert result["window_days"] == 30
    assert result["article_count"] == 3
    assert result["label"] == "negative"
    assert result["engine"] == "ProsusAI/finbert"


def test_sentiment_route_returns_502_when_news_fails(
    client: TestClient, auth_headers: dict[str, str], fake_fund, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def failing_search_news(phrase: str, days: int = 30, limit: int = 15) -> list[dict]:
        raise httpx.ConnectError("offline")

    monkeypatch.setattr(sentiment_service, "search_news", failing_search_news)
    assert client.get("/api/v1/instruments/mf-123/sentiment", headers=auth_headers).status_code == 502
    # Failures aren't cached.
    assert "mf-123" not in sentiment_service._instrument_sentiment_cache._items


def test_sentiment_route_404_for_unknown_instrument(client: TestClient, auth_headers: dict[str, str]) -> None:
    assert client.get("/api/v1/instruments/stock-FAKE.NS/sentiment", headers=auth_headers).status_code == 404
