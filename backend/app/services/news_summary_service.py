"""Combined news summary for the instrument detail page (Phase 5).

Flow: gather recent candidate articles -> pick the top 5 by relevance +
recency (near-duplicate headlines removed) -> get each article's text
(publisher full text when robots.txt allows, else the RSS snippet, else
just the headline) -> ONE multi-document summary of all five via
`get_summarizer()`, plus a sentiment tag per article for the list shown
beneath it.

Only the Summarizer interface and factory are used here; swapping the
extractive baseline for our trained model is a config change.
"""

import asyncio
import hashlib
import json
import logging
import math
import re
import threading
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx

from app.core.cache import MISSING, TTLCache
from app.core.config import settings
from app.core.constants import TICKER_TO_COMPANY_NAME
from app.data.news_repository import get_recent_articles_for_ticker
from app.services.article_fetcher import USER_AGENT, fetch_article_text
from app.services.instrument_service import get_instrument, parse_instrument_id
from app.services.news_service import search_bing_news, search_news
from app.services.sentiment_service import (
    article_text,
    fund_news_phrase,
    score_texts,
    sentiment_from_probabilities,
)
from app.services.summarization import SummaryFailure, SummaryInput, get_summarizer

logger = logging.getLogger(__name__)

TOP_N = 5
CANDIDATE_DAYS = 14
RECENCY_HALF_LIFE_DAYS = 3.0  # a 3-day-old article gets half the recency score
NAME_MATCH_WEIGHT = 1.0
RECENCY_WEIGHT = 1.0
HAS_TEXT_BONUS = 0.5  # prefer articles with text to summarize over headline-only ones
HEADLINE_DUPLICATE_THRESHOLD = 0.6
FETCH_CONCURRENCY = 5
# Each article contributes at most its first N words: leads carry the key
# facts, and it stops one long article from dominating the combined summary.
MAX_WORDS_PER_ARTICLE = 300

_REPO_ROOT = Path(__file__).resolve().parents[3]
_TOKEN = re.compile(r"[a-z0-9]+")
_HEADLINE_STOP = {"the", "a", "an", "of", "to", "in", "on", "for", "and", "at", "as", "is", "with", "by", "from"}

_ttl_seconds = settings.summarizer_cache_ttl_min * 60
_candidate_cache = TTLCache(ttl_seconds=_ttl_seconds, max_items=256)
_input_cache = TTLCache(ttl_seconds=_ttl_seconds, max_items=2048)  # url -> (text, input_kind)
_digest_cache = TTLCache(ttl_seconds=_ttl_seconds, max_items=512)  # article set -> response
_log_lock = threading.Lock()


# --- Selection -------------------------------------------------------------------

def headline_tokens(title: str) -> set[str]:
    return {t for t in _TOKEN.findall(title.lower()) if t not in _HEADLINE_STOP}


def relevance_score(article: dict, name_tokens: set[str], now: datetime) -> float:
    title_tokens = headline_tokens(article["title"])
    name_match = len(name_tokens & title_tokens) / len(name_tokens) if name_tokens else 0.0
    age_days = max(0.0, (now - article["published_at"]).total_seconds() / 86400)
    recency = math.pow(0.5, age_days / RECENCY_HALF_LIFE_DAYS)
    has_text = HAS_TEXT_BONUS if article.get("description") else 0.0
    return NAME_MATCH_WEIGHT * name_match + RECENCY_WEIGHT * recency + has_text


# Search engines also return fund/stock *product pages* (price, NAV, expense
# ratio listings). They aren't news, so they're dropped before ranking.
_LISTING_PAGE = re.compile(
    r"(share price, returns|expense ratio|explore list of|fund managers and other information|"
    r"invest in .{0,60} now|check (the )?latest nav|nav, returns|scheme details|fact ?sheet)",
    re.IGNORECASE,
)


_LISTING_TITLE_WORDS = {
    "growth", "direct", "regular", "plan", "option", "idcw", "dividend", "nav", "share", "price",
    "stock", "fund", "etf", "ltd", "limited", "dir", "g", "scheme", "exchange", "traded", "today",
}


def is_listing_page(article: dict, name: str) -> bool:
    if _LISTING_PAGE.search(article.get("description") or ""):
        return True
    # A headline that is only the instrument's name plus plan/listing words
    # ("SBI Gold ETF - Growth", "Titan share price today") is a product page.
    extra = headline_tokens(article["title"]) - headline_tokens(name)
    return extra <= _LISTING_TITLE_WORDS


def _jaccard(a: set[str], b: set[str]) -> float:
    return len(a & b) / len(a | b) if a and b else 0.0


def pick_top_articles(candidates: list[dict], name: str, now: datetime, n: int = TOP_N) -> list[dict]:
    """Highest relevance + recency first; a headline too similar to one
    already picked is skipped (the better-scored copy wins)."""
    name_tokens = headline_tokens(name)
    unique = {
        a["url"]: a for a in candidates if a.get("url") and a.get("title") and not is_listing_page(a, name)
    }.values()
    ranked = sorted(unique, key=lambda a: relevance_score(a, name_tokens, now), reverse=True)
    picked: list[dict] = []
    picked_tokens: list[set[str]] = []
    for article in ranked:
        tokens = headline_tokens(article["title"])
        if any(_jaccard(tokens, other) >= HEADLINE_DUPLICATE_THRESHOLD for other in picked_tokens):
            continue
        picked.append(article)
        picked_tokens.append(tokens)
        if len(picked) == n:
            break
    return picked


# --- Candidates --------------------------------------------------------------------

def _as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


async def _gather_candidates(instrument_id: str) -> tuple[str, list[dict]]:
    """(name used for relevance, candidate articles). Each source is
    optional: one failing just means fewer candidates."""
    cached = _candidate_cache.get(instrument_id)
    if cached is not MISSING:
        return cached

    kind, ref = parse_instrument_id(instrument_id)
    since = datetime.now(UTC) - timedelta(days=CANDIDATE_DAYS)
    if kind == "stock":
        name = TICKER_TO_COMPANY_NAME.get(ref, ref)
        sources = [get_recent_articles_for_ticker(ref, since), search_bing_news(name, days=CANDIDATE_DAYS)]
    else:
        name = fund_news_phrase((await get_instrument(instrument_id))["name"])
        sources = [search_bing_news(name, days=CANDIDATE_DAYS), search_news(name, days=CANDIDATE_DAYS)]

    candidates: list[dict] = []
    for result in await asyncio.gather(*sources, return_exceptions=True):
        if isinstance(result, Exception):
            logger.warning("News source failed for %s summaries: %s", instrument_id, result)
            continue
        # Mongo returns naive UTC datetimes; RSS parsing returns aware ones.
        candidates.extend({**a, "published_at": _as_utc(a["published_at"])} for a in result)

    _candidate_cache.set(instrument_id, (name, candidates))
    return name, candidates


# --- Inputs, cache, log ---------------------------------------------------------------

def digest_cache_key(urls: list[str], fingerprint: str, max_words: int) -> str:
    return hashlib.sha256(f"{'|'.join(sorted(urls))}|{fingerprint}|{max_words}".encode()).hexdigest()


async def _article_inputs(articles: list[dict]) -> list[tuple[str, str]]:
    """(text, input_kind) per article: full_text > snippet > headline.
    Each article's result is cached, so a changed top-5 only fetches the new ones."""
    semaphore = asyncio.Semaphore(FETCH_CONCURRENCY)

    async with httpx.AsyncClient(headers={"User-Agent": USER_AGENT}, follow_redirects=True) as client:

        async def one(article: dict) -> tuple[str, str]:
            cached = _input_cache.get(article["url"])
            if cached is not MISSING:
                return cached
            async with semaphore:
                full_text = await fetch_article_text(article["url"], client)
            if full_text:
                result = (full_text, "full_text")
            elif article.get("description"):
                result = (article["description"], "snippet")
            else:
                result = (article["title"], "headline")
            _input_cache.set(article["url"], result)
            return result

        return await asyncio.gather(*(one(a) for a in articles))


def _log_path() -> Path:
    path = Path(settings.summary_log_path)
    return path if path.is_absolute() else _REPO_ROOT / path


def log_summary(record: dict) -> None:
    """Append one JSONL line (only when LOG_SUMMARIES=true). Builds a
    corpus of real inputs + baseline outputs for training/evaluating our model."""
    path = _log_path()
    line = json.dumps(record, ensure_ascii=False, default=str)
    with _log_lock:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")


def _limit_words(text: str, max_words: int) -> str:
    words = text.split()
    return text if len(words) <= max_words else " ".join(words[:max_words])


def _tag_articles(articles: list[dict]) -> tuple[list[dict], str]:
    """Per-article sentiment tags with the same engine as the sentiment section."""
    probabilities, engine = score_texts([article_text(a) for a in articles])
    tagged = []
    for article, probs in zip(articles, probabilities, strict=True):
        sentiment = sentiment_from_probabilities(probs)
        tagged.append({**article, "label": sentiment["label"], "score": sentiment["score"]})
    return tagged, engine


# --- Entry point -------------------------------------------------------------------------

async def get_news_digest(instrument_id: str) -> dict:
    """One combined summary of the top 5 articles, plus those 5 articles
    (headline, source, date, sentiment tag) for the list beneath it."""
    summarizer = get_summarizer()
    max_words = settings.summarizer_max_words
    fingerprint = summarizer.cache_fingerprint()

    name, candidates = await _gather_candidates(instrument_id)
    top = pick_top_articles(candidates, name, datetime.now(UTC))
    result = {
        "instrument_id": instrument_id,
        "provider": summarizer.provider,
        "method": summarizer.method,
        "max_words": max_words,
        "summary": None,
        "word_count": 0,
        "summary_failed": False,
        "sources": {"full_text": 0, "snippet": 0, "headline": 0},
        "sentiment_engine": None,
        "articles": [],
        "generated_at": datetime.now(UTC),
    }
    if not top:
        return result

    key = digest_cache_key([a["url"] for a in top], fingerprint, max_words)
    cached = _digest_cache.get(key)
    if cached is not MISSING:
        return {**cached, "generated_at": datetime.now(UTC)}

    inputs = await _article_inputs(top)
    # Summarize the articles that have text; headline-only articles stay in
    # the list but only feed the summary when nothing else has any text.
    with_text = [text for text, kind in inputs if kind != "headline"]
    documents = tuple(_limit_words(text, MAX_WORDS_PER_ARTICLE) for text in (with_text or [t for t, _ in inputs]))
    request = SummaryInput(
        title=name,
        text="\n".join(documents),
        max_words=max_words,
        instrument_name=name,
        documents=documents,
    )
    (summary,), (tagged, engine) = await asyncio.gather(
        asyncio.to_thread(summarizer.summarize_batch, [request]),
        asyncio.to_thread(_tag_articles, top),
    )

    for _, kind in inputs:
        result["sources"][kind] += 1
    result["sentiment_engine"] = engine
    result["articles"] = [
        {
            "title": a["title"],
            "url": a["url"],
            "source": a.get("source"),
            "published_at": a["published_at"],
            "input_kind": kind,
            "label": a["label"],
            "score": a["score"],
        }
        for a, (_, kind) in zip(tagged, inputs, strict=True)
    ]

    if isinstance(summary, SummaryFailure):
        # Still show the article list; failures aren't cached so the next request retries.
        result["summary_failed"] = True
        return result

    result["summary"] = summary.summary
    result["word_count"] = summary.word_count
    _digest_cache.set(key, result)
    if settings.log_summaries:
        await asyncio.to_thread(
            log_summary,
            {
                "timestamp": datetime.now(UTC).isoformat(),
                "kind": "multi_article_digest",
                "instrument_id": instrument_id,
                "url": key,  # stable id for this set of articles (eval script dedupes on it)
                "article_urls": [a["url"] for a in top],
                "input_kinds": [kind for _, kind in inputs],
                "title": name,
                "article_text": request.text,
                "documents": list(documents),
                "summary": summary.summary,
                "provider": summary.provider,
                "method": summary.method,
                "algorithm_version": fingerprint,
                "max_words": max_words,
                "latency_ms": summary.latency_ms,
            },
        )
    return result
