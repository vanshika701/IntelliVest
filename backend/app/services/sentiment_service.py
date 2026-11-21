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
from datetime import UTC, datetime, timedelta
from pathlib import Path

from app.core.config import settings
from app.data.news_repository import (
    find_articles_needing_sentiment,
    get_scored_articles_for_ticker,
    set_article_sentiments,
)

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


def _load_model() -> bool:
    """Load FinBERT once. Returns False (and logs) if it can't be loaded —
    e.g. no internet on the very first run — so the caller can skip this
    run and retry next time instead of crashing the job."""
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
