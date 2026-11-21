"""Unit tests — exercise RSS entry parsing and ticker matching alone, with
fabricated feed entries instead of real HTTP calls."""

import time
from datetime import UTC

from app.services.news_service import match_tickers, parse_feed_entries

PUBLISHED = time.strptime("2026-01-01 12:00:00", "%Y-%m-%d %H:%M:%S")


def test_parse_skips_entries_missing_link_or_published() -> None:
    entries = [
        {"link": "https://example.com/a", "title": "Infosys wins deal", "published_parsed": PUBLISHED},
        {"title": "Infosys untraceable", "published_parsed": PUBLISHED},
        {"link": "https://example.com/c", "title": "Infosys no timestamp"},
    ]

    records = parse_feed_entries(entries, "Economic Times")

    assert len(records) == 1
    record = records[0]
    assert record["url"] == "https://example.com/a"
    assert record["source"] == "Economic Times"
    assert record["tickers"] == ["INFY.NS"]
    assert record["published_at"].tzinfo == UTC


def test_general_feed_drops_untracked_and_price_tracker_entries() -> None:
    entries = [
        {"link": "https://example.com/a", "title": "Sensex ends flat", "published_parsed": PUBLISHED},
        {
            "link": "https://example.com/tracker",
            "title": "Sun Pharma Share Price Live Updates: Sun Pharma Stock Price History",
            "published_parsed": PUBLISHED,
        },
        {
            "link": "https://example.com/b",
            "title": "TCS and Wipro lead IT rally",
            "summary": "<p>Heavyweights <b>HDFC Bank</b> also gained.</p>",
            "published_parsed": PUBLISHED,
        },
    ]

    records = parse_feed_entries(entries, "Livemint")

    assert [r["url"] for r in records] == ["https://example.com/b"]
    assert records[0]["tickers"] == ["HDFCBANK.NS", "TCS.NS", "WIPRO.NS"]
    assert records[0]["description"] == "Heavyweights HDFC Bank also gained."


def test_google_news_entry_uses_real_publisher_and_search_ticker() -> None:
    entries = [
        {
            "link": "https://news.google.com/rss/articles/abc",
            "title": "Q3 results beat estimates - Business Standard",
            "summary": '<a href="https://news.google.com/rss/articles/abc">Q3 results beat estimates</a>',
            "source": {"title": "Business Standard"},
            "published_parsed": PUBLISHED,
        }
    ]

    records = parse_feed_entries(entries, None, ticker="TITAN.NS")

    assert len(records) == 1
    record = records[0]
    assert record["title"] == "Q3 results beat estimates"
    assert record["source"] == "Business Standard"
    assert record["description"] is None
    assert record["tickers"] == ["TITAN.NS"]


def test_match_tickers_excludes_separately_listed_group_companies() -> None:
    assert match_tickers("Reliance Power shares surge") == []
    assert match_tickers("SBI Life posts profit") == []
    assert match_tickers("L&T Finance raises funds") == []
    assert match_tickers("ITC Hotels demerger completes") == []
    assert match_tickers("Reliance, L&T and SBI drag Nifty") == ["RELIANCE.NS", "SBIN.NS", "LT.NS"]


def test_match_tickers_requires_whole_words() -> None:
    assert match_tickers("Switch to titanium") == []
    assert match_tickers("Titan shares rise") == ["TITAN.NS"]
