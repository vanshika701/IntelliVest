"""Unit test — exercises article parsing alone, with a fabricated NewsAPI
response instead of a real HTTP call."""

from datetime import timezone

from app.services.news_service import parse_articles


def test_parse_articles_skips_entries_missing_url_or_published_at() -> None:
    raw_articles = [
        {
            "url": "https://example.com/a",
            "title": "Reliance posts strong quarter",
            "description": "desc",
            "content": "content",
            "source": {"name": "Example News"},
            "publishedAt": "2026-01-01T12:00:00Z",
        },
        {
            # Missing url entirely — can't dedupe on this, must be skipped.
            "title": "Untraceable article",
            "publishedAt": "2026-01-01T12:00:00Z",
        },
        {
            "url": "https://example.com/c",
            "title": "No timestamp",
            # Missing publishedAt — can't sort/query on this, must be skipped.
        },
    ]

    records = parse_articles("RELIANCE.NS", raw_articles)

    assert len(records) == 1
    record = records[0]
    assert record["url"] == "https://example.com/a"
    assert record["source"] == "Example News"
    assert record["tickers"] == ["RELIANCE.NS"]
    assert record["published_at"].tzinfo == timezone.utc
