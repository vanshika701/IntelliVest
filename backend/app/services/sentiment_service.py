"""Service layer for FinBERT news sentiment (Phase 5).

Uses the pretrained ProsusAI/finbert model as-is (inference only — no
training happens here). The model is downloaded once into
ml/models/hf_cache/ on first use and loaded lazily, so the API starts
fast and tests never load it.

Scoring runs as a background step after each news ingestion: it finds
articles not yet scored by the current model, classifies them in a
worker thread (FinBERT inference is CPU-bound and would otherwise block
the API's event loop), and stores the result on the article itself so
read endpoints only ever read precomputed data.
"""

import asyncio
import logging
import os
import re
import threading
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx

from app.core.cache import MISSING, TTLCache
from app.core.config import settings
from app.data.news_repository import (
    find_articles_needing_sentiment,
    get_scored_articles_for_ticker,
    set_article_sentiments,
)
from app.services.instrument_service import DataProviderError, get_instrument, parse_instrument_id
from app.services.news_service import search_news

# Windows without Developer Mode can't create the symlinks the Hugging Face
# cache prefers; it falls back to copying, which is fine — skip the warning.
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")

logger = logging.getLogger(__name__)

# backend/app/services/this_file.py -> parents[3] is the repo root.
_MODEL_CACHE_DIR = Path(__file__).resolve().parents[3] / "ml" / "models" / "hf_cache"

BATCH_SIZE = 16
MAX_TOKENS = 256
SCORE_RUN_LIMIT = 500

# A ticker's average score (positive minus negative probability, -1..1)
# has to clear this margin to be called positive/negative overall.
OVERALL_LABEL_THRESHOLD = 0.15

_tokenizer = None
_model = None
# The scheduler job, the startup warm-up and on-demand fund sentiment can
# all ask for the model at once; only one of them should load it.
_load_lock = threading.Lock()


def _load_model() -> bool:
    """Load FinBERT once. Returns False (and logs) if it can't be loaded —
    e.g. no internet on the very first run — so the caller can skip this
    run and retry next time instead of crashing the job."""
    with _load_lock:
        return _load_model_locked()


def _load_model_locked() -> bool:
    global _tokenizer, _model
    if _model is not None:
        return True
    try:
        from transformers import AutoModelForSequenceClassification, AutoTokenizer
        from transformers.utils import logging as hf_logging

        hf_logging.disable_progress_bar()
        _tokenizer = AutoTokenizer.from_pretrained(settings.sentiment_model, cache_dir=_MODEL_CACHE_DIR)
        _model = AutoModelForSequenceClassification.from_pretrained(
            settings.sentiment_model, cache_dir=_MODEL_CACHE_DIR
        ).eval()
    except Exception:
        logger.exception("Could not load sentiment model %s — skipping scoring", settings.sentiment_model)
        _tokenizer = _model = None
        return False
    logger.info("Sentiment model %s loaded", settings.sentiment_model)
    return True


def classify(texts: list[str]) -> list[dict[str, float]]:
    """Class probabilities per text, e.g. {"positive": 0.9, "negative": 0.05,
    "neutral": 0.05}. Label names come from the model's own config, so a
    fine-tuned replacement with a different label order still works."""
    import torch

    id2label = _model.config.id2label
    results = []
    with torch.inference_mode():
        for start in range(0, len(texts), BATCH_SIZE):
            batch = texts[start : start + BATCH_SIZE]
            inputs = _tokenizer(batch, padding=True, truncation=True, max_length=MAX_TOKENS, return_tensors="pt")
            probs = torch.softmax(_model(**inputs).logits, dim=-1).tolist()
            results += [{id2label[i].lower(): p for i, p in enumerate(row)} for row in probs]
    return results


# Fallback engine when FinBERT can't be loaded: a small finance keyword
# lexicon. Crude, but honest about being crude (reported as engine "lexicon").
_POSITIVE_WORDS = {
    "gain", "gains", "surge", "surges", "rally", "rallies", "jump", "jumps", "rise", "rises",
    "beat", "beats", "record", "high", "upgrade", "upgraded", "profit", "growth", "strong",
    "soar", "soars", "outperform", "bullish", "inflows", "boost", "wins", "win",
}
_NEGATIVE_WORDS = {
    "fall", "falls", "drop", "drops", "decline", "declines", "loss", "losses", "slump", "slumps",
    "miss", "misses", "downgrade", "downgraded", "plunge", "plunges", "weak", "cut", "cuts",
    "fraud", "probe", "bearish", "outflows", "crash", "low", "concern", "concerns", "sell-off",
}


def lexicon_classify(texts: list[str]) -> list[dict[str, float]]:
    results = []
    for text in texts:
        words = re.findall(r"[a-z\-]+", text.lower())
        pos = sum(w in _POSITIVE_WORDS for w in words)
        neg = sum(w in _NEGATIVE_WORDS for w in words)
        if pos == neg:
            results.append({"positive": 0.1, "negative": 0.1, "neutral": 0.8})
        elif pos > neg:
            results.append({"positive": 0.7, "negative": 0.1, "neutral": 0.2})
        else:
            results.append({"positive": 0.1, "negative": 0.7, "neutral": 0.2})
    return results


def score_texts(texts: list[str]) -> tuple[list[dict[str, float]], str]:
    """The one entry point for scoring arbitrary text: FinBERT if it can be
    loaded, else the lexicon. Returns (probabilities per text, engine).
    Blocking — call it via asyncio.to_thread from async code."""
    if _load_model():
        return classify(texts), settings.sentiment_model
    return lexicon_classify(texts), "lexicon"


def sentiment_from_probabilities(probs: dict[str, float]) -> dict:
    return {
        "label": max(probs, key=probs.get),
        "score": round(probs.get("positive", 0.0) - probs.get("negative", 0.0), 4),
        "probabilities": {label: round(p, 4) for label, p in probs.items()},
    }


def article_text(article: dict) -> str:
    title = (article.get("title") or "").strip()
    description = (article.get("description") or "").strip()
    return f"{title}. {description}" if description else title


async def score_pending_articles() -> int:
    """Score every article not yet scored by the current model, newest
    first, SCORE_RUN_LIMIT at a time. Returns how many were scored."""
    if not await asyncio.to_thread(_load_model):
        return 0

    model_name = settings.sentiment_model
    total = 0
    while True:
        articles = await find_articles_needing_sentiment(model_name, SCORE_RUN_LIMIT)
        if not articles:
            break

        probabilities = await asyncio.to_thread(classify, [article_text(a) for a in articles])
        scored_at = datetime.now(UTC)
        updates = [
            (a["_id"], {**sentiment_from_probabilities(p), "model": model_name, "scored_at": scored_at})
            for a, p in zip(articles, probabilities, strict=True)
        ]
        total += await set_article_sentiments(updates)
        if len(articles) < SCORE_RUN_LIMIT:
            break

    logger.info("Sentiment scoring complete: %d articles scored with %s", total, model_name)
    return total


def overall_label(average_score: float | None) -> str | None:
    if average_score is None:
        return None
    if average_score > OVERALL_LABEL_THRESHOLD:
        return "positive"
    if average_score < -OVERALL_LABEL_THRESHOLD:
        return "negative"
    return "neutral"


async def summarize_ticker_sentiment(ticker: str, days: int = 7, top_n: int = 3) -> dict:
    """Per-stock sentiment view: label counts, average score, overall
    label and the most recent scored articles over the last `days`."""
    articles = await get_scored_articles_for_ticker(ticker, datetime.now(UTC) - timedelta(days=days))

    label_counts = {"positive": 0, "negative": 0, "neutral": 0}
    for article in articles:
        label = article["sentiment"]["label"]
        label_counts[label] = label_counts.get(label, 0) + 1

    average = round(sum(a["sentiment"]["score"] for a in articles) / len(articles), 4) if articles else None
    return {
        "ticker": ticker,
        "window_days": days,
        "article_count": len(articles),
        "label_counts": label_counts,
        "average_score": average,
        "overall_label": overall_label(average),
        "recent_articles": [
            {
                "title": a["title"],
                "url": a["url"],
                "source": a.get("source"),
                "published_at": a["published_at"],
                "label": a["sentiment"]["label"],
                "score": a["sentiment"]["score"],
            }
            for a in articles[:top_n]
        ],
    }


# --- Sentiment for any instrument (detail page) ---

MIN_ARTICLES_FOR_LABEL = 3
INSTRUMENT_SENTIMENT_TTL_SECONDS = 20 * 60
_instrument_sentiment_cache = TTLCache(ttl_seconds=INSTRUMENT_SENTIMENT_TTL_SECONDS, max_items=256)


def fund_news_phrase(scheme_name: str) -> str:
    """'SBI GOLD FUND - Direct Plan - Growth' -> 'SBI GOLD FUND': the plan
    and option suffixes never appear in news headlines."""
    return scheme_name.split(" - ")[0].strip()


def _aggregate(articles: list[dict], engine: str, window_days: int, instrument_id: str) -> dict:
    count = len(articles)
    average = round(sum(a["score"] for a in articles) / count, 4) if count else None
    has_enough = count >= MIN_ARTICLES_FOR_LABEL
    return {
        "instrument_id": instrument_id,
        "label": overall_label(average) if has_enough else None,
        "average_score": average if has_enough else None,
        "article_count": count,
        "min_articles": MIN_ARTICLES_FOR_LABEL,
        "window_days": window_days,
        "engine": engine,
        "articles": articles[:8],
        "generated_at": datetime.now(UTC),
    }


async def _stock_articles(ticker: str) -> tuple[list[dict], str, int]:
    """Stored FinBERT-scored articles: last 7 days, widened to 30 if thin."""
    for days in (7, 30):
        stored = await get_scored_articles_for_ticker(ticker, datetime.now(UTC) - timedelta(days=days))
        if len(stored) >= MIN_ARTICLES_FOR_LABEL or days == 30:
            break
    articles = [
        {
            "title": a["title"],
            "url": a["url"],
            "source": a.get("source"),
            "published_at": a["published_at"],
            "label": a["sentiment"]["label"],
            "score": a["sentiment"]["score"],
        }
        for a in stored
    ]
    engine = stored[0]["sentiment"].get("model", settings.sentiment_model) if stored else settings.sentiment_model
    return articles, engine, days


async def _fund_articles(scheme_name: str) -> tuple[list[dict], str, int]:
    """Fresh Google News search for the fund's name, scored on the spot."""
    days = 30
    try:
        news = await search_news(fund_news_phrase(scheme_name), days=days)
    except httpx.HTTPError as exc:
        raise DataProviderError("News is unavailable right now") from exc
    if not news:
        return [], settings.sentiment_model, days

    probabilities, engine = await asyncio.to_thread(score_texts, [article_text(n) for n in news])
    articles = []
    for item, probs in zip(news, probabilities, strict=True):
        sentiment = sentiment_from_probabilities(probs)
        articles.append(
            {
                "title": item["title"],
                "url": item["url"],
                "source": item.get("source"),
                "published_at": item["published_at"],
                "label": sentiment["label"],
                "score": sentiment["score"],
            }
        )
    return articles, engine, days


async def get_instrument_sentiment(instrument_id: str) -> dict:
    """Overall Negative/Neutral/Positive label plus the headlines behind it.
    `label` is None when there are fewer than MIN_ARTICLES_FOR_LABEL
    headlines. Cached for 20 minutes per instrument; failures aren't cached."""
    cached = _instrument_sentiment_cache.get(instrument_id)
    if cached is not MISSING:
        return cached

    kind, ref = parse_instrument_id(instrument_id)
    if kind == "stock":
        articles, engine, days = await _stock_articles(ref)
    else:
        instrument = await get_instrument(instrument_id)
        articles, engine, days = await _fund_articles(instrument["name"])

    result = _aggregate(articles, engine, days, instrument_id)
    _instrument_sentiment_cache.set(instrument_id, result)
    return result


def warm_up_model() -> None:
    """Load FinBERT in the background at startup so the first on-demand
    fund sentiment request doesn't wait ~20 s for it."""
    _load_model()
