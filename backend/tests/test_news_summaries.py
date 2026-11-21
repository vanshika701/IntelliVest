"""News summary pipeline tests: article fetching/extraction (mock HTTP),
candidate selection, the service's fallbacks/caching/logging/isolation,
and the endpoint. No real network calls."""

import json
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from fastapi.testclient import TestClient

from app.api.v1.routes import instruments as instruments_routes
from app.core.config import settings
from app.services import article_fetcher, news_summary_service
from app.services.article_fetcher import extract_article_text, fetch_article_text
from app.services.news_service import resolve_bing_link
from app.services.news_summary_service import get_news_summaries, is_listing_page, pick_top_articles
from app.services.summarization import Summarizer, SummaryInput, SummaryResult

NOW = datetime(2026, 11, 21, 12, 0, tzinfo=UTC)
BODY = " ".join(
    f"Paragraph sentence {i} explains how Infosys grew revenue and won large deals this quarter." for i in range(12)
)


@pytest.fixture(autouse=True)
def _fresh_state():
    article_fetcher._robots_cache.clear()
    news_summary_service._candidate_cache.clear()
    news_summary_service._summary_cache.clear()
    instruments_routes._summaries_limiter.reset()


# --- Extraction -------------------------------------------------------------------

def test_extract_prefers_json_ld_article_body() -> None:
    html = (
        '<html><head><script type="application/ld+json">'
        + json.dumps({"@context": "https://schema.org", "@type": "NewsArticle", "articleBody": BODY})
        + "</script></head><body><p>Short teaser about something else entirely here.</p></body></html>"
    )
    assert extract_article_text(html) == BODY


def test_extract_picks_the_main_body_not_related_story_teasers() -> None:
    main = "".join(f"<p>Main story paragraph {i} about Infosys results and the deal pipeline outlook.</p>" for i in range(8))
    teasers = "".join(f"<li><p>Related: another unrelated story headline number {i} here.</p></li>" for i in range(5))
    html = f"<html><body><nav><p>Home Markets News Opinion Videos Podcasts</p></nav><div class='story'>{main}</div><ul>{teasers}</ul></body></html>"
    text = extract_article_text(html)
    assert text.startswith("Main story paragraph 0")
    assert "Related:" not in text


def test_extract_returns_none_for_thin_pages() -> None:
    assert extract_article_text("<html><body><p>Enable JavaScript to view this page properly please.</p></body></html>") is None


# --- Fetching (mock transport) ---------------------------------------------------------

def _client(robots: httpx.Response, page: httpx.Response | None = None, calls: list | None = None) -> httpx.AsyncClient:
    def handler(request: httpx.Request) -> httpx.Response:
        if calls is not None:
            calls.append(request.url.path)
        if request.url.path == "/robots.txt":
            return robots
        return page or httpx.Response(200, headers={"content-type": "text/html"}, text=f"<div>{''.join(f'<p>{BODY}</p>' for _ in range(1))}</div>")

    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


async def test_fetch_returns_text_when_robots_allows() -> None:
    client = _client(httpx.Response(200, text="User-agent: *\nDisallow: /private/"))
    assert await fetch_article_text("https://news.example.com/markets/story", client) == BODY


async def test_fetch_respects_robots_disallow() -> None:
    calls: list = []
    client = _client(httpx.Response(200, text="User-agent: *\nDisallow: /"), calls=calls)
    assert await fetch_article_text("https://news.example.com/markets/story", client) is None
    assert calls == ["/robots.txt"]  # the article itself was never requested


async def test_missing_robots_means_allowed_but_robots_errors_mean_disallowed() -> None:
    assert await fetch_article_text("https://a.example.com/story", _client(httpx.Response(404))) == BODY
    assert await fetch_article_text("https://b.example.com/story", _client(httpx.Response(503))) is None


async def test_fetch_never_touches_google_news_and_survives_errors() -> None:
    calls: list = []
    client = _client(httpx.Response(200, text=""), calls=calls)
    assert await fetch_article_text("https://news.google.com/rss/articles/abc", client) is None
    assert calls == []

    def boom(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("slow", request=request)

    assert await fetch_article_text("https://c.example.com/x", httpx.AsyncClient(transport=httpx.MockTransport(boom))) is None


async def test_fetch_rejects_non_html() -> None:
    client = _client(httpx.Response(404), httpx.Response(200, headers={"content-type": "application/pdf"}, content=b"%PDF"))
    assert await fetch_article_text("https://d.example.com/report.pdf", client) is None


def test_resolve_bing_link_decodes_publisher_url() -> None:
    link = "http://www.bing.com/news/apiclick.aspx?ref=FexRss&url=https%3a%2f%2fwww.livemint.com%2fmarket%2fstory.html&c=1"
    assert resolve_bing_link(link) == "https://www.livemint.com/market/story.html"
    assert resolve_bing_link("http://www.bing.com/news/apiclick.aspx?url=javascript%3aalert(1)") is None


# --- Selection ---------------------------------------------------------------------------

def _article(title: str, hours_old: float, url: str | None = None, description: str | None = None) -> dict:
    return {
        "title": title,
        "url": url or f"https://example.com/{abs(hash(title))}",
        "source": "Mint",
        "description": description,
        "published_at": NOW - timedelta(hours=hours_old),
    }


def test_pick_top_dedupes_near_duplicate_headlines_and_caps_at_five() -> None:
    candidates = [
        _article("Infosys wins $2 billion deal from European bank", 1, description="Text."),
        _article("Infosys wins $2 billion deal from a European bank", 2),
        *[
            _article(title, 3 + i)
            for i, title in enumerate(
                [
                    "Infosys margins seen stable by brokerages",
                    "Infosys hires 5,000 freshers in Bengaluru",
                    "Infosys shares hit one-month low",
                    "Infosys expands Japan presence with NTT Docomo",
                    "Infosys CEO comments on AI demand",
                    "Infosys board approves interim dividend",
                ]
            )
        ],
    ]
    picked = pick_top_articles(candidates, "Infosys", NOW)
    titles = [a["title"] for a in picked]
    assert len(picked) == 5
    assert titles[0] == "Infosys wins $2 billion deal from European bank"
    assert "Infosys wins $2 billion deal from a European bank" not in titles


def test_pick_top_prefers_recent_relevant_articles_with_text() -> None:
    old = _article("Infosys quarterly results analysis deep dive", 24 * 10, description="Some text.")
    fresh_with_text = _article("Infosys shares rise after deal announcement", 2, description="Some text.")
    fresh_headline = _article("Infosys shares rise after the deal win today", 1)
    unrelated = _article("Gold prices hit record as dollar weakens", 1, description="Text.")
    picked = pick_top_articles([old, fresh_headline, unrelated, fresh_with_text], "Infosys", NOW, n=2)
    assert [a["title"] for a in picked] == [fresh_with_text["title"], old["title"]]


def test_listing_pages_are_not_news() -> None:
    assert is_listing_page(_article("SBI Gold ETF", 1, description="Get share price, returns, expense ratio"), "SBI Gold ETF")
    assert is_listing_page(_article("SBI Gold ETF - Growth", 1), "SBI Gold ETF")
    assert is_listing_page(_article("Titan share price today", 1), "Titan")
    assert not is_listing_page(_article("SBI Gold ETF sees record inflows as prices climb", 1), "SBI Gold ETF")
    # Short real headlines are still news.
    assert not is_listing_page(_article("Infosys wins deal", 1), "Infosys")


# --- Service -------------------------------------------------------------------------------

class FakeSummarizer(Summarizer):
    provider = "fake"
    method = "fake@1"

    def __init__(self) -> None:
        self.calls = 0

    def summarize(self, item: SummaryInput) -> SummaryResult:
        self.calls += 1
        if "explode" in item.title:
            raise RuntimeError("model failure")
        summary = f"summary of {item.text or item.title}"[:200]
        return SummaryResult(summary, len(summary.split()), self.provider, self.method, 1.0)


@pytest.fixture
def pipeline(monkeypatch: pytest.MonkeyPatch, tmp_path):
    articles = [
        _article("Infosys wins deal", 1, url="https://a.example/1"),
        _article("Infosys margins explode higher", 2, url="https://a.example/2", description="A snippet."),
        _article("Infosys hires", 3, url="https://a.example/3", description="Another snippet."),
    ]
    for a in articles:
        a["published_at"] = datetime.now(UTC) - (NOW - a["published_at"])
    summarizer = FakeSummarizer()
    input_calls: list = []

    async def fake_candidates(instrument_id: str):
        return "Infosys", articles

    async def fake_inputs(batch: list[dict]):
        input_calls.append([a["url"] for a in batch])
        return [
            ("Full article body text.", "full_text") if a["url"].endswith("/1")
            else (a["description"], "snippet") if a.get("description")
            else ("", "headline")
            for a in batch
        ]

    monkeypatch.setattr(news_summary_service, "_gather_candidates", fake_candidates)
    monkeypatch.setattr(news_summary_service, "_article_inputs", fake_inputs)
    monkeypatch.setattr(news_summary_service, "get_summarizer", lambda: summarizer)
    monkeypatch.setattr(settings, "summary_log_path", str(tmp_path / "log.jsonl"))
    return {"summarizer": summarizer, "input_calls": input_calls, "log": tmp_path / "log.jsonl"}


async def test_service_marks_input_kinds_and_isolates_failures(pipeline, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "log_summaries", False)
    result = await get_news_summaries("stock-INFY.NS")
    items = {i["url"]: i for i in result["items"]}

    assert items["https://a.example/1"]["input_kind"] == "full_text"
    assert items["https://a.example/1"]["used_fallback"] is False
    assert items["https://a.example/3"]["input_kind"] == "snippet"
    assert items["https://a.example/3"]["used_fallback"] is True
    # The failing item falls back to its headline; the others are unaffected.
    failed = items["https://a.example/2"]
    assert failed["summary_failed"] is True
    assert failed["summary"] == "Infosys margins explode higher"
    assert sum(not i["summary_failed"] for i in result["items"]) == 2
    assert result["provider"] == "fake" and result["max_words"] == settings.summarizer_max_words
    assert not pipeline["log"].exists()


async def test_service_caches_successes_but_retries_failures(pipeline, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "log_summaries", False)
    await get_news_summaries("stock-INFY.NS")
    await get_news_summaries("stock-INFY.NS")
    # Second call only re-processes the item whose summary failed.
    assert pipeline["input_calls"][1] == ["https://a.example/2"]


async def test_service_logs_jsonl_when_enabled(pipeline, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "log_summaries", True)
    await get_news_summaries("stock-INFY.NS")
    lines = [json.loads(line) for line in pipeline["log"].read_text(encoding="utf-8").splitlines()]
    assert len(lines) == 2  # failures aren't logged
    assert {"article_text", "summary", "method", "algorithm_version", "timestamp"} <= lines[0].keys()


async def test_service_returns_empty_items_when_no_news(monkeypatch: pytest.MonkeyPatch) -> None:
    async def no_candidates(instrument_id: str):
        return "Infosys", []

    monkeypatch.setattr(news_summary_service, "_gather_candidates", no_candidates)
    result = await get_news_summaries("stock-INFY.NS")
    assert result["items"] == []


# --- Endpoint ------------------------------------------------------------------------------

def test_endpoint_404_for_unknown_instrument(client: TestClient, auth_headers: dict) -> None:
    assert client.get("/api/v1/instruments/stock-FAKE.NS/news-summaries", headers=auth_headers).status_code == 404


def test_endpoint_returns_summaries_and_is_rate_limited(
    client: TestClient, auth_headers: dict, pipeline, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "log_summaries", False)
    monkeypatch.setattr(instruments_routes._summaries_limiter, "max_requests", 2)

    first = client.get("/api/v1/instruments/stock-INFY.NS/news-summaries", headers=auth_headers)
    assert first.status_code == 200
    assert len(first.json()["items"]) == 3
    assert client.get("/api/v1/instruments/stock-INFY.NS/news-summaries", headers=auth_headers).status_code == 200

    limited = client.get("/api/v1/instruments/stock-INFY.NS/news-summaries", headers=auth_headers)
    assert limited.status_code == 429
    assert int(limited.headers["Retry-After"]) >= 1
