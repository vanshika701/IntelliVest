"""Service layer for news ingestion.

Seam between Indian financial news RSS feeds and storage
(app/data/news_repository.py) — parsing/validation lives here. No API
key and no daily quota, unlike the NewsAPI pipeline this replaced.

Two kinds of feed:
- General market feeds (Economic Times, Livemint): each item is tagged
  with every tracked company its headline/description mentions (via
  TICKER_ALIASES); items mentioning none are dropped.
- One Google News search per company: targeted coverage for each ticker,
  including outlets whose own feeds block automated requests.
"""

import calendar
import logging
import re
from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs, quote_plus, urlparse

import feedparser
import httpx
from bs4 import BeautifulSoup

from app.core.constants import NEWS_RSS_FEEDS, TICKER_ALIASES, TICKER_TO_COMPANY_NAME
from app.core.retry import with_retry
from app.data.news_repository import upsert_news_articles
from app.services.ingestion_types import IngestResult

logger = logging.getLogger(__name__)

GOOGLE_NEWS_SEARCH_URL = "https://news.google.com/rss/search?q={query}&hl=en-IN&gl=IN&ceid=IN:en"

# Some publishers reject httpx's default User-Agent outright.
_HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; IntelliVestBot/0.1)"}

# Auto-generated price-tracker pages (mostly Economic Times) that look like
# articles but carry no news — they'd skew sentiment and summaries.
_PRICE_TRACKER_TITLE = re.compile(
    r"Share Price (?:Live Updates|Highlights|Today)|Stock Price History", re.IGNORECASE
)

_TICKER_PATTERNS: dict[str, re.Pattern] = {
    ticker: re.compile(rf"(?<!\w)(?:{'|'.join(aliases)})(?!\w)", re.IGNORECASE)
    for ticker, aliases in TICKER_ALIASES.items()
}


def match_tickers(text: str) -> list[str]:
    return [ticker for ticker, pattern in _TICKER_PATTERNS.items() if pattern.search(text)]


def _clean_text(raw: str | None) -> str | None:
    if not raw:
        return None
    text = BeautifulSoup(raw, "html.parser").get_text(" ", strip=True) if "<" in raw else raw.strip()
    return text or None


def parse_feed_entries(
    entries: list[dict],
    feed_source: str | None,
    ticker: str | None = None,
    keep_untagged: bool = False,
) -> list[dict]:
    """Turn RSS entries (as parsed by feedparser) into storage-ready records.

    `ticker` is set for a per-company search feed: every entry is tagged
    with it, on top of any other companies the text mentions. Entries that
    match no tracked company are dropped unless `keep_untagged` is set.
    """
    records = []
    for entry in entries:
        url = entry.get("link")
        published = entry.get("published_parsed")
        # url is our dedup key, published_at is what every "recent news"
        # query sorts on — an entry missing either isn't usable.
        if not url or not published:
            continue

        # Google News names the real publisher per entry and appends it to
        # the title ("Headline - Publisher").
        source = (entry.get("source") or {}).get("title") or feed_source
        title = (entry.get("title") or "").strip()
        if source:
            title = title.removesuffix(f" - {source}")
        if _PRICE_TRACKER_TITLE.search(title):
            continue

        description = _clean_text(entry.get("summary"))
        # Google News descriptions are just a link back to the headline.
        if title and description and description.startswith(title):
            description = None

        tickers = set(match_tickers(f"{title} {description or ''}"))
        if ticker:
            tickers.add(ticker)
        if not tickers and not keep_untagged:
            continue

        records.append(
            {
                "url": url,
                "title": title,
                "description": description,
                "source": source,
                "published_at": datetime.fromtimestamp(calendar.timegm(published), tz=UTC),
                "tickers": sorted(tickers),
            }
        )
    return records


@with_retry
async def fetch_feed(client: httpx.AsyncClient, url: str) -> list[dict]:
    response = await client.get(url)
    response.raise_for_status()
    return feedparser.parse(response.content).entries


async def ingest_feed(
    client: httpx.AsyncClient,
    label: str,
    url: str,
    feed_source: str | None,
    ticker: str | None = None,
) -> IngestResult:
    """Fetch and store one feed. Failures are isolated per feed: one
    publisher being down shouldn't abort the whole run."""
    try:
        entries = await fetch_feed(client, url)
        records = parse_feed_entries(entries, feed_source, ticker)
        upserted = await upsert_news_articles(records)
        return IngestResult(label, upserted)
    except httpx.HTTPStatusError as exc:
        logger.exception("News feed request failed for %s", label)
        return IngestResult(label, 0, error=f"HTTP {exc.response.status_code}")
    except Exception as exc:
        logger.exception("Failed to ingest news feed %s", label)
        return IngestResult(label, 0, error=str(exc))


def google_news_url(company_name: str, days: int = 7) -> str:
    return GOOGLE_NEWS_SEARCH_URL.format(query=quote_plus(f'"{company_name}" when:{days}d'))


BING_NEWS_SEARCH_URL = "https://www.bing.com/news/search?q={query}&format=rss&mkt=en-in"


def resolve_bing_link(link: str) -> str | None:
    """Bing RSS links are click-trackers carrying the publisher URL in their
    `url` query parameter; decode it locally (no request to Bing)."""
    params = parse_qs(urlparse(link).query)
    target = (params.get("url") or [None])[0]
    return target if target and target.startswith(("http://", "https://")) else None


def _normalise_bing_entries(entries: list[dict]) -> list[dict]:
    normalised = []
    for entry in entries:
        url = resolve_bing_link(entry.get("link") or "")
        if not url:
            continue
        normalised.append({**entry, "link": url, "source": {"title": entry.get("news_source")}})
    return normalised


async def search_bing_news(phrase: str, days: int = 30, limit: int = 15) -> list[dict]:
    """On-demand Bing News search (allowed by bing.com/robots.txt). Unlike
    Google News, items carry the publisher's real URL and a short
    description, so there's text to summarize. Not stored. Raises httpx
    errors on failure."""
    url = BING_NEWS_SEARCH_URL.format(query=quote_plus(f'"{phrase}"'))
    async with httpx.AsyncClient(timeout=10.0, headers=_HEADERS, follow_redirects=True) as client:
        entries = await fetch_feed(client, url)
    records = parse_feed_entries(_normalise_bing_entries(entries), None, keep_untagged=True)
    cutoff = datetime.now(UTC) - timedelta(days=days)
    records = [r for r in records if r["published_at"] >= cutoff]
    records.sort(key=lambda r: r["published_at"], reverse=True)
    return records[:limit]


async def search_news(phrase: str, days: int = 30, limit: int = 15) -> list[dict]:
    """On-demand Google News search for an exact phrase (e.g. a fund name),
    newest first. Not stored. Raises httpx errors on failure."""
    async with httpx.AsyncClient(timeout=10.0, headers=_HEADERS, follow_redirects=True) as client:
        entries = await fetch_feed(client, google_news_url(phrase, days))
    records = parse_feed_entries(entries, None, keep_untagged=True)
    records.sort(key=lambda r: r["published_at"], reverse=True)
    return records[:limit]


async def ingest_news_for_universe(tickers: list[str]) -> list[IngestResult]:
    feeds: list[tuple[str, str, str | None, str | None]] = [
        (url, url, publisher, None) for publisher, url in NEWS_RSS_FEEDS
    ]
    feeds += [
        (ticker, google_news_url(TICKER_TO_COMPANY_NAME.get(ticker, ticker)), None, ticker)
        for ticker in tickers
    ]

    results = []
    async with httpx.AsyncClient(timeout=15.0, headers=_HEADERS, follow_redirects=True) as client:
        for label, url, feed_source, ticker in feeds:
            result = await ingest_feed(client, label, url, feed_source, ticker)
            results.append(result)
            status = f"error: {result.error}" if result.error else "ok"
            logger.info(
                "Ingested news feed %s: %d articles upserted (%s)",
                label,
                result.records_upserted,
                status,
            )
    return results
