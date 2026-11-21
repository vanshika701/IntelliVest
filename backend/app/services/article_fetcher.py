"""Fetch the full text of a news article from the publisher, politely.

- Respects robots.txt (cached per host for 6 h). If robots.txt can't be
  read for a reason other than "not found", the site is treated as
  disallowed — conservative by design.
- Never fetches aggregator pages (Google News forbids crawling; Bing links
  are decoded to the publisher URL before they get here).
- Short timeouts and a size cap; any failure returns None so callers fall
  back to the RSS snippet or headline. It never raises.
"""

import asyncio
import json
import logging
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

import httpx
from bs4 import BeautifulSoup

from app.core.cache import MISSING, TTLCache

logger = logging.getLogger(__name__)

USER_AGENT = "Mozilla/5.0 (compatible; IntelliVestBot/0.1; student project)"
ROBOTS_AGENT = "IntelliVestBot"
BLOCKED_HOSTS = {"news.google.com", "www.bing.com", "bing.com", "www.msn.com"}
FETCH_TIMEOUT_SECONDS = 6.0
ROBOTS_TIMEOUT_SECONDS = 4.0
MAX_BYTES = 2_000_000
MIN_ARTICLE_WORDS = 60
MAX_ARTICLE_WORDS = 1200
MIN_PARAGRAPH_WORDS = 8

_robots_cache = TTLCache(ttl_seconds=6 * 60 * 60, max_items=256)
_NOISE_TAGS = ["script", "style", "noscript", "nav", "header", "footer", "aside", "form", "figure", "iframe", "svg", "button"]


def _host(url: str) -> str:
    return urlparse(url).netloc.lower()


async def robots_allows(client: httpx.AsyncClient, url: str) -> bool:
    parsed = urlparse(url)
    origin = f"{parsed.scheme}://{parsed.netloc}"
    parser = _robots_cache.get(origin)
    if parser is MISSING:
        parser = RobotFileParser()
        try:
            response = await client.get(f"{origin}/robots.txt", timeout=ROBOTS_TIMEOUT_SECONDS)
            if response.status_code == 200:
                parser.parse(response.text.splitlines())
            elif response.status_code in (404, 410):
                parser.allow_all = True
            else:
                parser.disallow_all = True
        except httpx.HTTPError:
            parser.disallow_all = True
        _robots_cache.set(origin, parser)
    return parser.can_fetch(ROBOTS_AGENT, url)


def _words(text: str) -> int:
    return len(text.split())


def _from_json_ld(soup: BeautifulSoup) -> str | None:
    """Many news sites embed the full body as schema.org articleBody."""
    for tag in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(tag.string or "")
        except (json.JSONDecodeError, TypeError):
            continue
        nodes = data if isinstance(data, list) else data.get("@graph", [data]) if isinstance(data, dict) else []
        for node in nodes:
            body = node.get("articleBody") if isinstance(node, dict) else None
            if isinstance(body, str) and _words(body) >= MIN_ARTICLE_WORDS:
                return body
    return None


def _from_paragraphs(soup: BeautifulSoup) -> str | None:
    """Pick the single element whose direct <p> children hold the most
    text — the article body — rather than every <p> on the page (which
    sweeps in related-story teasers)."""
    for tag in soup(_NOISE_TAGS):
        tag.decompose()
    words_by_parent: dict[int, int] = {}
    paragraphs_by_parent: dict[int, list[str]] = {}
    for p in soup.find_all("p"):
        text = p.get_text(" ", strip=True)
        if _words(text) < MIN_PARAGRAPH_WORDS:
            continue
        key = id(p.parent)
        words_by_parent[key] = words_by_parent.get(key, 0) + _words(text)
        paragraphs_by_parent.setdefault(key, []).append(text)
    if not words_by_parent:
        return None
    best = max(words_by_parent, key=words_by_parent.get)
    text = "\n".join(paragraphs_by_parent[best])
    return text if _words(text) >= MIN_ARTICLE_WORDS else None


def extract_article_text(html: str) -> str | None:
    soup = BeautifulSoup(html, "html.parser")
    text = _from_json_ld(soup) or _from_paragraphs(soup)
    if not text:
        return None
    words = text.split()
    # Leads carry the key facts; capping keeps summarization fast.
    return text if len(words) <= MAX_ARTICLE_WORDS else " ".join(words[:MAX_ARTICLE_WORDS])


async def fetch_article_text(url: str, client: httpx.AsyncClient | None = None) -> str | None:
    """Full article text, or None if not allowed / not fetchable / not
    extractable. Never raises."""
    if not url.startswith(("http://", "https://")) or _host(url) in BLOCKED_HOSTS:
        return None
    own_client = client is None
    client = client or httpx.AsyncClient(headers={"User-Agent": USER_AGENT}, follow_redirects=True)
    try:
        if not await robots_allows(client, url):
            return None
        async with client.stream("GET", url, timeout=FETCH_TIMEOUT_SECONDS) as response:
            if response.status_code != 200 or "html" not in response.headers.get("content-type", ""):
                return None
            if _host(str(response.url)) in BLOCKED_HOSTS:
                return None
            body = bytearray()
            async for chunk in response.aiter_bytes():
                body.extend(chunk)
                if len(body) > MAX_BYTES:
                    return None
        html = body.decode(response.encoding or "utf-8", errors="replace")
        return await asyncio.to_thread(extract_article_text, html)
    except (httpx.HTTPError, UnicodeError, ValueError) as exc:
        logger.info("Article fetch failed for %s: %s", url, exc)
        return None
    finally:
        if own_client:
            await client.aclose()
