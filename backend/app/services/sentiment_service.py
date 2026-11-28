"""Service layer for news sentiment (Phase 5).

Uses pretrained Hugging Face models as-is (inference only — no training
happens here). The default is settings.sentiment_model (DistilRoBERTa
fine-tuned on financial news, which won the 2026-11-28 comparison, see
ml/log.md); settings.sentiment_extra_models (FinBERT) can be picked per
request. The default model's score is stored in each article's
`sentiment` field, which every other module reads; each extra model's in
`sentiments.<key>`. The model is downloaded once into
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

# Model name -> (tokenizer, model), loaded on first use.
_loaded: dict[str, tuple] = {}
# The scheduler job, the startup warm-up and on-demand fund sentiment can
# all ask for a model at once; only one of them should load it.
_load_lock = threading.Lock()

# Labels for the model picker; other ids are shown as they are.
KNOWN_MODELS: dict[str, tuple[str, str]] = {
    "mrm8488/distilroberta-finetuned-financial-news-sentiment-analysis": (
        "DistilRoBERTa (financial news)",
        "86.7% on 30 Indian market headlines, 75.7% on 1,000 financial tweets; 2x faster",
    ),
    "ProsusAI/finbert": (
        "FinBERT",
        "83.3% on 30 Indian market headlines, 72.7% on 1,000 financial tweets",
    ),
}


class UnknownSentimentModel(ValueError):
    """A sentiment model that isn't offered (settings.sentiment_model or
    settings.sentiment_extra_models)."""


def sentiment_models() -> list[str]:
    """Every model offered, the default first."""
    extras = [m.strip() for m in settings.sentiment_extra_models.split(",") if m.strip()]
    return list(dict.fromkeys([settings.sentiment_model, *extras]))


def resolve_sentiment_model(model: str | None) -> str:
    if not model:
        return settings.sentiment_model
    if model not in sentiment_models():
        raise UnknownSentimentModel(f"Unknown sentiment model {model!r}; choose {', '.join(sentiment_models())}")
    return model


def storage_field(model: str) -> str:
    """Where an article keeps this model's score: `sentiment` for the
    default model (what every other module reads), else `sentiments.<key>`."""
    if model == settings.sentiment_model:
        return "sentiment"
    return "sentiments." + re.sub(r"[^A-Za-z0-9]+", "_", model).strip("_")


def available_sentiment_models() -> list[dict]:
    return [
        {
            "key": name,
            "label": KNOWN_MODELS.get(name, (name, ""))[0],
            "description": KNOWN_MODELS.get(name, ("", "Hugging Face model"))[1],
            "version": None,
            "available": True,
            "default": name == settings.sentiment_model,
        }
        for name in sentiment_models()
    ]


def _load_model(model: str | None = None) -> bool:
    """Load a model once (default: the default model). Returns False (and
    logs) if it can't be loaded — e.g. no internet on the very first run —
    so the caller can skip this run and retry next time instead of crashing."""
    with _load_lock:
        return _load_model_locked(model or settings.sentiment_model)


def _load_model_locked(name: str) -> bool:
    if name in _loaded:
        return True
    try:
        from transformers import AutoModelForSequenceClassification, AutoTokenizer
        from transformers.utils import logging as hf_logging

        hf_logging.disable_progress_bar()
        tokenizer = AutoTokenizer.from_pretrained(name, cache_dir=_MODEL_CACHE_DIR)
        model = AutoModelForSequenceClassification.from_pretrained(name, cache_dir=_MODEL_CACHE_DIR).eval()
    except Exception:
        logger.exception("Could not load sentiment model %s — skipping scoring", name)
        return False
    _loaded[name] = (tokenizer, model)
    logger.info("Sentiment model %s loaded", name)
    return True


def model_revision(model: str | None = None) -> str | None:
    """The exact Hugging Face commit of the loaded model, if known."""
    loaded = _loaded.get(model or settings.sentiment_model)
    return getattr(getattr(loaded[1], "config", None), "_commit_hash", None) if loaded else None


def classify(texts: list[str], model: str | None = None) -> list[dict[str, float]]:
    """Class probabilities per text, e.g. {"positive": 0.9, "negative": 0.05,
    "neutral": 0.05}, from a loaded model (default: the default model).
    Label names come from the model's own config, so models with different
    label orders all work."""
    import torch

    tokenizer, net = _loaded[model or settings.sentiment_model]
    id2label = net.config.id2label
    results = []
    with torch.inference_mode():
        for start in range(0, len(texts), BATCH_SIZE):
            batch = texts[start : start + BATCH_SIZE]
            inputs = tokenizer(batch, padding=True, truncation=True, max_length=MAX_TOKENS, return_tensors="pt")
            probs = torch.softmax(net(**inputs).logits, dim=-1).tolist()
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


def score_texts(texts: list[str], model: str | None = None) -> tuple[list[dict[str, float]], str]:
    """The one entry point for scoring arbitrary text: `model` (default:
    the default model) if it can be loaded, else the lexicon. Returns
    (probabilities per text, engine). Blocking — call it via
    asyncio.to_thread from async code."""
    name = model or settings.sentiment_model
    if _load_model(name):
        return classify(texts, name), name
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
    """Score every article not yet scored by each offered model, newest
    first, SCORE_RUN_LIMIT at a time. Returns how many scores were stored
    (an article scored by two models counts twice)."""
    total = 0
    for model_name in sentiment_models():
        if await asyncio.to_thread(_load_model, model_name):
            total += await _score_pending_with(model_name)
    return total


async def _score_pending_with(model_name: str) -> int:
    field = storage_field(model_name)
    total = 0
    while True:
        articles = await find_articles_needing_sentiment(model_name, SCORE_RUN_LIMIT, field)
        if not articles:
            break

        probabilities = await asyncio.to_thread(classify, [article_text(a) for a in articles], model_name)
        scored_at = datetime.now(UTC)
        updates = [
            (
                a["_id"],
                {
                    **sentiment_from_probabilities(p),
                    "model": model_name,
                    # Phase 10 records which exact weights scored the evidence.
                    "revision": model_revision(model_name),
                    "scored_at": scored_at,
                },
            )
            for a, p in zip(articles, probabilities, strict=True)
        ]
        total += await set_article_sentiments(updates, field)
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


async def _stock_articles(ticker: str, model: str) -> tuple[list[dict], str, int]:
    """Stored articles scored by `model`: last 7 days, widened to 30 if thin."""
    for days in (7, 30):
        stored = await get_scored_articles_for_ticker(
            ticker, datetime.now(UTC) - timedelta(days=days), storage_field(model)
        )
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
    engine = stored[0]["sentiment"].get("model", model) if stored else model
    return articles, engine, days


async def _fund_articles(scheme_name: str, model: str) -> tuple[list[dict], str, int]:
    """Fresh Google News search for the fund's name, scored on the spot."""
    days = 30
    try:
        news = await search_news(fund_news_phrase(scheme_name), days=days)
    except httpx.HTTPError as exc:
        raise DataProviderError("News is unavailable right now") from exc
    if not news:
        return [], model, days

    probabilities, engine = await asyncio.to_thread(score_texts, [article_text(n) for n in news], model)
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


async def get_instrument_sentiment(instrument_id: str, model: str | None = None) -> dict:
    """Overall Negative/Neutral/Positive label plus the headlines behind it,
    from `model` (default: the default model). `label` is None when there
    are fewer than MIN_ARTICLES_FOR_LABEL headlines. Cached for 20 minutes
    per instrument and model; failures aren't cached. Raises
    UnknownSentimentModel for a model that isn't offered."""
    name = resolve_sentiment_model(model)
    cache_key = f"{instrument_id}|{name}"
    cached = _instrument_sentiment_cache.get(cache_key)
    if cached is not MISSING:
        return cached

    kind, ref = parse_instrument_id(instrument_id)
    if kind == "stock":
        articles, engine, days = await _stock_articles(ref, name)
    else:
        instrument = await get_instrument(instrument_id)
        articles, engine, days = await _fund_articles(instrument["name"], name)

    result = {
        **_aggregate(articles, engine, days, instrument_id),
        "model": name,
        "model_label": KNOWN_MODELS.get(name, (name, ""))[0],
    }
    _instrument_sentiment_cache.set(cache_key, result)
    return result


def warm_up_model() -> None:
    """Load the default sentiment model in the background at startup so
    the first on-demand fund sentiment request doesn't wait ~20 s for it."""
    _load_model()
