"""Service layer for news ingestion.

Seam between the external API (NewsAPI, called here over HTTP) and
storage (app/data/news_repository.py) — parsing/validation lives here.
"""

import logging
from datetime import datetime

import httpx

from app.core.config import settings
from app.core.constants import TICKER_TO_COMPANY_NAME
from app.data.news_repository import upsert_news_articles
from app.services.ingestion_types import IngestResult

logger = logging.getLogger(__name__)

NEWSAPI_URL = "https://newsapi.org/v2/everything"


def parse_articles(ticker: str, raw_articles: list[dict]) -> list[dict]:
    """Turn NewsAPI's raw article payload into clean, storage-ready records."""
    records = []
    for article in raw_articles:
        url = article.get("url")
        published_at_raw = article.get("publishedAt")
        # Both fields are load-bearing: url is our dedup key, published_at
        # is what every later "recent news" query sorts on. An article
        # missing either isn't usable.
        if not url or not published_at_raw:
            continue

        published_at = datetime.fromisoformat(published_at_raw.replace("Z", "+00:00"))
        records.append(
            {
                "url": url,
                "title": article.get("title"),
                "description": article.get("description"),
                "content": article.get("content"),
                "source": (article.get("source") or {}).get("name"),
                "published_at": published_at,
                "tickers": [ticker],
            }
        )
    return records


async def fetch_news_for_ticker(
    client: httpx.AsyncClient, ticker: str, company_name: str, page_size: int = 20
) -> list[dict]:
    response = await client.get(
        NEWSAPI_URL,
        params={
            "q": company_name,
            "language": "en",
            "sortBy": "publishedAt",
            "pageSize": page_size,
            "apiKey": settings.news_api_key,
        },
    )
    response.raise_for_status()
    payload = response.json()
    return parse_articles(ticker, payload.get("articles", []))


async def ingest_news_for_ticker(
    client: httpx.AsyncClient, ticker: str, company_name: str
) -> IngestResult:
    """Fetch and store news for a single ticker.

    Failures are isolated per-ticker, same reasoning as market data: one
    ticker hitting a transient error shouldn't abort the whole run.
    """
    try:
        records = await fetch_news_for_ticker(client, ticker, company_name)
        if not records:
            return IngestResult(ticker, 0, error="No articles found")

        upserted = await upsert_news_articles(records)
        return IngestResult(ticker, upserted)
    except httpx.HTTPStatusError as exc:
        logger.exception("NewsAPI request failed for %s", ticker)
        return IngestResult(ticker, 0, error=f"HTTP {exc.response.status_code}")
    except Exception as exc:
        logger.exception("Failed to ingest news for %s", ticker)
        return IngestResult(ticker, 0, error=str(exc))


async def ingest_news_for_universe(tickers: list[str]) -> list[IngestResult]:
    if not settings.news_api_key:
        logger.warning(
            "NEWS_API_KEY is not set — skipping news ingestion. "
            "Add it to backend/.env to enable this."
        )
        return []

    results = []
    async with httpx.AsyncClient(timeout=10.0) as client:
        for ticker in tickers:
            company_name = TICKER_TO_COMPANY_NAME.get(ticker, ticker)
            result = await ingest_news_for_ticker(client, ticker, company_name)
            results.append(result)
            status = f"error: {result.error}" if result.error else "ok"
            logger.info(
                "Ingested news for %s: %d articles upserted (%s)",
                ticker,
                result.records_upserted,
                status,
            )
    return results
