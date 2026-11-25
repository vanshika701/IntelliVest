"""News summary pipeline tests: article fetching/extraction (mock HTTP),
candidate selection, the service's fallbacks/caching/logging/isolation,
and the endpoint. No real network calls."""

import json
from datetime import UTC, date, datetime, timedelta

import httpx
import pytest
from fastapi.testclient import TestClient

from app.api.v1.routes import instruments as instruments_routes
from app.core.config import settings
from app.services import article_fetcher, news_summary_service
from app.services.article_fetcher import extract_article_text, fetch_article_text
from app.services.news_service import resolve_bing_link
from app.services.news_summary_service import (
    get_news_digest,
    is_listing_page,
    mentions_instrument,
    pick_top_articles,
    text_matches_headline,
)
from app.services.news_topics import topic_for_fund, topic_for_stock
from app.services.price_move import build_price_move
from app.services.summarization import Summarizer, SummaryInput, SummaryResult

NOW = datetime(2026, 11, 21, 12, 0, tzinfo=UTC)
BODY = " ".join(
    f"Paragraph sentence {i} explains how Infosys grew revenue and won large deals this quarter." for i in range(12)
)


@pytest.fixture(autouse=True)
def _fresh_state():
    article_fetcher._robots_cache.clear()
    news_summary_service._candidate_cache.clear()
    news_summary_service._input_cache.clear()
    news_summary_service._digest_cache.clear()
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
    assert is_listing_page(_article("ICICI Prudential Silver ETF FOF Growth", 1), "ICICI PRUDENTIAL SILVER ETF")
    # Short real headlines are still news.
    assert not is_listing_page(_article("Infosys wins deal", 1), "Infosys")


# --- Service -------------------------------------------------------------------------------

class FakeSummarizer(Summarizer):
    provider = "fake"
    method = "fake@1"

    def __init__(self, fail: bool = False) -> None:
        self.fail = fail
        self.requests: list[SummaryInput] = []

    def summarize(self, item: SummaryInput) -> SummaryResult:
        self.requests.append(item)
        if self.fail:
            raise RuntimeError("model failure")
        summary = "combined summary of " + str(len(item.documents)) + " articles"
        return SummaryResult(summary, len(summary.split()), self.provider, self.method, 1.0)


@pytest.fixture
def pipeline(monkeypatch: pytest.MonkeyPatch, tmp_path):
    now = datetime.now(UTC)
    articles = [
        {"title": "Infosys wins deal", "url": "https://a.example/1", "source": "Mint", "description": None, "published_at": now - timedelta(hours=1)},
        {"title": "Infosys margins improve", "url": "https://a.example/2", "source": "ET", "description": "A snippet.", "published_at": now - timedelta(hours=2)},
        {"title": "Infosys hires freshers", "url": "https://a.example/3", "source": "BL", "description": None, "published_at": now - timedelta(hours=3)},
    ]
    state = {"summarizer": FakeSummarizer(), "input_calls": [], "log": tmp_path / "log.jsonl"}

    async def fake_candidates(instrument_id: str):
        return "Infosys", articles, None

    async def fake_inputs(batch: list[dict]):
        state["input_calls"].append([a["url"] for a in batch])
        kinds = {"https://a.example/1": ("Full article body text.", "full_text"),
                 "https://a.example/2": ("A snippet.", "snippet"),
                 "https://a.example/3": ("Infosys hires freshers", "headline")}
        return [kinds[a["url"]] for a in batch]

    def fake_scores(texts: list[str]):
        return [{"positive": 0.8, "negative": 0.1, "neutral": 0.1} for _ in texts], "fake-finbert"

    async def fake_move(instrument_id: str):
        return None

    monkeypatch.setattr(news_summary_service, "get_price_move", fake_move)
    monkeypatch.setattr(news_summary_service, "_gather_candidates", fake_candidates)
    monkeypatch.setattr(news_summary_service, "_article_inputs", fake_inputs)
    monkeypatch.setattr(news_summary_service, "score_texts", fake_scores)
    monkeypatch.setattr(news_summary_service, "get_summarizer", lambda: state["summarizer"])
    monkeypatch.setattr(settings, "summary_log_path", str(state["log"]))
    monkeypatch.setattr(settings, "log_summaries", False)
    return state


async def test_digest_is_one_summary_plus_tagged_articles(pipeline) -> None:
    result = await get_news_digest("stock-INFY.NS")

    assert result["summary"] == "combined summary of 2 articles"
    assert result["summary_failed"] is False
    assert result["sources"] == {"full_text": 1, "snippet": 1, "headline": 1}
    assert result["sentiment_engine"] == "fake-finbert"
    # Ranked by relevance + recency + has-text, so the snippet article leads.
    assert [a["url"] for a in result["articles"]] == ["https://a.example/2", "https://a.example/1", "https://a.example/3"]
    assert all(a["label"] == "positive" for a in result["articles"])
    assert [a["input_kind"] for a in result["articles"]] == ["snippet", "full_text", "headline"]


async def test_headline_only_articles_stay_out_of_the_summary_when_others_have_text(pipeline) -> None:
    await get_news_digest("stock-INFY.NS")
    request = pipeline["summarizer"].requests[0]
    assert request.documents == ("A snippet.", "Full article body text.")
    assert request.instrument_name == "Infosys"
    assert request.max_words == settings.summarizer_max_words


async def test_headlines_are_used_when_nothing_has_text(pipeline, monkeypatch: pytest.MonkeyPatch) -> None:
    async def headlines_only(batch: list[dict]):
        return [(a["title"], "headline") for a in batch]

    monkeypatch.setattr(news_summary_service, "_article_inputs", headlines_only)
    await get_news_digest("stock-INFY.NS")
    assert pipeline["summarizer"].requests[0].documents == ("Infosys margins improve", "Infosys wins deal", "Infosys hires freshers")


async def test_summarizer_failure_still_returns_the_article_list(pipeline) -> None:
    pipeline["summarizer"].fail = True
    result = await get_news_digest("stock-INFY.NS")
    assert result["summary"] is None
    assert result["summary_failed"] is True
    assert len(result["articles"]) == 3
    # Failures aren't cached: the next request tries again.
    await get_news_digest("stock-INFY.NS")
    assert len(pipeline["summarizer"].requests) == 2


async def test_digest_is_cached_by_article_set(pipeline) -> None:
    await get_news_digest("stock-INFY.NS")
    await get_news_digest("stock-INFY.NS")
    assert len(pipeline["input_calls"]) == 1
    assert len(pipeline["summarizer"].requests) == 1


async def test_digest_logs_one_jsonl_line_when_enabled(pipeline, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "log_summaries", True)
    await get_news_digest("stock-INFY.NS")
    lines = [json.loads(line) for line in pipeline["log"].read_text(encoding="utf-8").splitlines()]
    assert len(lines) == 1
    assert lines[0]["kind"] == "multi_article_digest"
    assert lines[0]["article_urls"] == ["https://a.example/2", "https://a.example/1", "https://a.example/3"]
    assert {"article_text", "documents", "summary", "method", "algorithm_version", "timestamp", "url"} <= lines[0].keys()
    assert lines[0]["documents"] == ["A snippet.", "Full article body text."]


async def test_digest_without_news(monkeypatch: pytest.MonkeyPatch) -> None:
    async def no_candidates(instrument_id: str):
        return "Infosys", [], None

    async def no_move(instrument_id: str):
        return None

    monkeypatch.setattr(news_summary_service, "get_price_move", no_move)
    monkeypatch.setattr(news_summary_service, "_gather_candidates", no_candidates)
    result = await get_news_digest("stock-INFY.NS")
    assert result["summary"] is None and result["articles"] == [] and result["summary_failed"] is False


# --- Endpoint ------------------------------------------------------------------------------

def test_endpoint_404_for_unknown_instrument(client: TestClient, auth_headers: dict) -> None:
    assert client.get("/api/v1/instruments/stock-FAKE.NS/news-summary", headers=auth_headers).status_code == 404


def test_endpoint_returns_digest_and_is_rate_limited(
    client: TestClient, auth_headers: dict, pipeline, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(instruments_routes._summaries_limiter, "max_requests", 2)

    first = client.get("/api/v1/instruments/stock-INFY.NS/news-summary", headers=auth_headers)
    assert first.status_code == 200
    body = first.json()
    assert body["summary"] == "combined summary of 2 articles"
    assert len(body["articles"]) == 3
    assert client.get("/api/v1/instruments/stock-INFY.NS/news-summary", headers=auth_headers).status_code == 200

    limited = client.get("/api/v1/instruments/stock-INFY.NS/news-summary", headers=auth_headers)
    assert limited.status_code == 429
    assert int(limited.headers["Retry-After"]) >= 1


# --- Regression: the SBI Gold summary quoted the journalist's bio ----------------------------

def _mint_like_page() -> str:
    story = "".join(
        f"<div class='row'><div class='storyParagraph'><p>Fund managers raise gold and silver exposure, part {i}, as the price correction "
        "revives interest among multi-asset funds this month.</p></div></div>" for i in range(25)
    )
    bio = "Srushti is a markets reporter. Her work aims to drive impact. " * 18
    return f"<html><body><div id='story'>{story}</div><div class='CARD'><p>{bio}</p></div></body></html>"


def test_extract_prefers_wrapped_story_paragraphs_over_a_dense_bio() -> None:
    page = _mint_like_page()
    for html in (page, page.replace("CARD", "abtAuthorSlideItem")):
        text = extract_article_text(html)
        assert text.startswith("Fund managers raise gold")
        assert "reporter" not in text


def test_fetched_text_must_match_its_headline() -> None:
    title = "Fund managers look to raise gold, silver exposure as price correction revives interest"
    assert text_matches_headline("Fund managers are raising gold and silver exposure after a price correction.", title)
    assert not text_matches_headline("Srushti is a reporter. Her story on gold imports drove impact.", title)


def test_articles_must_mention_the_instrument() -> None:
    assert mentions_instrument(_article("Gold rallies as SBI Mutual Fund turns positive", 1), "SBI GOLD FUND", None)
    assert not mentions_instrument(_article("Invesco India Silver ETF Fund of Fund", 1), "SBI GOLD FUND", None)
    assert mentions_instrument(_article("SBI raises loan rates", 1), "State Bank of India", "SBIN.NS")
    assert not mentions_instrument(_article("Bank holiday today: are banks open?", 1), "State Bank of India", "SBIN.NS")


def test_tag_and_quote_pages_are_not_news() -> None:
    assert is_listing_page(_article("tcs coverage archive", 1, url="https://x.com/tag/tcs"), "TCS")
    assert is_listing_page(_article("TCS.NS stock price, news, quote and history", 1), "TCS")


# --- Sector / theme fallback ---------------------------------------------------------------

@pytest.mark.parametrize(
    ("name", "category", "expected"),
    [
        ("SBI GOLD FUND - Direct Plan - Growth", "Other Scheme - FoF Domestic", "Gold"),
        ("ICICI PRUDENTIAL SILVER ETF", "Other Scheme - Other  ETFs", "Silver"),
        ("Edelweiss Gold and Silver ETF FOF - Direct Plan", None, "Precious Metals"),
        ("Bandhan Nifty IT Index Fund - Regular Plan - Growth", "Other Scheme - Index Funds", "IT"),
        ("BANDHAN NIFTY BANK INDEX FUND - Regular Plan - Growth", "Other Scheme - Index Funds", "Banking"),
        ("Axis Banking & PSU Debt Fund - Direct Plan", "Debt Scheme", "Bonds & Interest Rates"),
        ("Nippon India Pharma Fund - Growth", "Equity Schemes - Sectoral Fund", "Pharma"),
        ("Axis Small Cap Fund - Regular Plan - Growth", "Equity Schemes - Small Cap Fund", "Small Caps"),
        ("Bandhan Nifty 50 Index Fund - Growth", "Other Scheme - Index Funds", "Indian Stock Market"),
        ("HDFC Flexi Cap Fund - Growth", "Equity Scheme - Flexi Cap Fund", "Indian Stock Market"),
        ("SBI Liquid Fund - Direct Plan", "Debt Scheme - Liquid Fund", "Bonds & Interest Rates"),
    ],
)
def test_topic_for_fund(name: str, category: str | None, expected: str) -> None:
    assert topic_for_fund(name, category).name == expected


def test_it_topic_ignores_the_word_it() -> None:
    topic = topic_for_stock("TCS.NS")
    assert topic.name == "IT"
    assert topic.matches("IT stocks rally") and not topic.matches("Is it time to sell gold?")


def _stub_sources(monkeypatch: pytest.MonkeyPatch, own: list[dict], related: list[dict]) -> None:
    async def fake_bing(phrase: str, days: int = 30, limit: int = 15):
        return own if "BANDHAN" in phrase.upper() else related

    async def fake_google(phrase: str, days: int = 30, limit: int = 15):
        return []

    async def fake_instrument(instrument_id: str):
        return {"name": "Bandhan Gold ETF - Growth", "category": None}

    monkeypatch.setattr(news_summary_service, "search_bing_news", fake_bing)
    monkeypatch.setattr(news_summary_service, "search_news", fake_google)
    monkeypatch.setattr(news_summary_service, "get_instrument", fake_instrument)


async def test_product_pages_trigger_the_theme_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    pages = [
        _article("Bandhan Gold ETF Regular-Growth", 1, description="SCHEMES MANAGED BY Abhishek Jain Bandhan Nifty 100"),
        _article("Bandhan Gold ETF Direct Plan Growth", 1, description="This scheme has consistently delivered"),
    ]
    related = [_article("Gold falls 3% as dollar firms", 1), _article("Cricket news roundup", 1)]
    _stub_sources(monkeypatch, pages, related)
    _, candidates, topic = await news_summary_service._gather_candidates("mf-1")
    assert topic.name == "Gold"
    assert {c["title"] for c in candidates} == {"Gold falls 3% as dollar firms"}


async def test_own_news_is_kept_when_there_is_enough(monkeypatch: pytest.MonkeyPatch) -> None:
    own = [_article("Bandhan Gold ETF sees record inflows", 1), _article("Bandhan launches offer, Gold ETF assets jump", 2)]
    _stub_sources(monkeypatch, own, [_article("Gold falls 3%", 1)])
    _, candidates, topic = await news_summary_service._gather_candidates("mf-1")
    assert topic is None and len(candidates) == 2


def test_events_outrank_listicles_and_roundups() -> None:
    event = _article("Titan shares fall 5% after weak Q2 results", 10, description="x")
    listicle = _article("Top 5 stocks to buy including Titan", 1, description="x")
    roundup = _article("Infosys, TCS, Wipro and Titan among movers", 1, description="x")
    picked = pick_top_articles([listicle, roundup, event], "Titan", NOW, n=1)
    assert picked == [event]


async def test_digest_reports_sector_scope(pipeline, monkeypatch: pytest.MonkeyPatch) -> None:
    async def related(instrument_id: str):
        _, articles, _ = await original(instrument_id)
        return "Bandhan Gold ETF", articles, topic_for_fund("Bandhan Gold ETF", None)

    original = news_summary_service._gather_candidates
    monkeypatch.setattr(news_summary_service, "_gather_candidates", related)
    result = await get_news_digest("mf-1")
    assert (result["scope"], result["scope_name"]) == ("sector", "Gold")
    assert pipeline["summarizer"].requests[0].instrument_name == "Gold"


def test_topic_news_is_indian_unless_the_fund_invests_abroad() -> None:
    pharma = topic_for_fund("Nippon India Pharma Fund", None)
    assert pharma.matches("Pharma stocks rally, Nifty Pharma up 11%")
    assert not pharma.matches("Pharma stocks: why the surge?", "The Nikkei 225 fell 2.78%")
    assert topic_for_fund("Motilal Nasdaq 100 FOF", None).matches("Nasdaq falls as tech sells off")


def test_exam_results_are_not_news() -> None:
    assert is_listing_page(_article("SBI Clerk Mains Result 2026 Out", 1), "State Bank of India")


# --- Price move -----------------------------------------------------------------------------

def _series(values: dict[int, float]) -> list[tuple[date, float]]:
    return [(date(2026, 11, 25) - timedelta(days=d), v) for d, v in sorted(values.items(), reverse=True)]


def test_price_move_states_direction_and_date() -> None:
    move = build_price_move(
        "SBI GOLD FUND - Direct Plan - Growth", _series({40: 125, 31: 125, 8: 110, 1: 101, 0: 100}), 100, date(2026, 11, 25), -0.99
    )
    assert move["text"] == (
        "SBI GOLD FUND: down 1.0% on the day, down 9.1% over a week and down 20.0% over a month (as of 25 Nov 2026)."
    )


def test_price_move_handles_flat_missing_and_split_data() -> None:
    flat = build_price_move("X", _series({8: 100, 0: 100.01}), 100.01, date(2026, 11, 25), 0.01)
    assert flat["text"] == "X: flat on the day and flat over a week (as of 25 Nov 2026)."
    split = build_price_move("X", _series({31: 1500, 8: 1500, 0: 100}), 100, date(2026, 11, 25), -0.5)
    assert split["week_pct"] is None and split["month_pct"] is None
    assert split["text"] == "X: down 0.5% on the day (as of 25 Nov 2026)."
    assert build_price_move("X", [], None, None, None) is None
    # A year-old price must not be passed off as "a week ago".
    assert build_price_move("X", _series({300: 90, 0: 100}), 100, date(2026, 11, 25), None) is None


async def test_digest_carries_the_price_move(pipeline, monkeypatch: pytest.MonkeyPatch) -> None:
    async def move(instrument_id: str):
        return {"text": "Infosys: up 3.8% on the day."}

    monkeypatch.setattr(news_summary_service, "get_price_move", move)
    assert (await get_news_digest("stock-INFY.NS"))["price_move"]["text"].startswith("Infosys: up")
