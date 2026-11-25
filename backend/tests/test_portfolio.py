"""Portfolio valuation and sector news."""

from datetime import UTC, date, datetime, timedelta

from app.core.constants import SECTOR_NEWS_QUERIES, SECTORS
from app.data.collections import get_investments_collection, get_news_collection
from app.data.news_repository import upsert_news_articles
from app.services import portfolio_service
from app.services.instrument_service import DataProviderError
from app.services.investment_service import list_investments
from app.services.news_service import is_sector_headline
from app.services.portfolio_service import build_holding, get_portfolio
from app.services.sector_service import sector_news

TODAY = date(2026, 11, 26)
BASE = {"user_id": "u", "instrument_id": "mf-1", "instrument_name": "Fund", "instrument_type": "MF"}
ORDER = {**BASE, "kind": "one_time", "status": "completed", "amount": 1000.0, "price_at_order": 10.0}
SIP = {
    **BASE, "kind": "sip", "status": "active", "amount": 500.0, "estimated_units": 50.0,
    "day_of_month": 10, "next_installment_date": "2026-10-10",
}  # fmt: skip


def test_gain_loss_and_break_even() -> None:
    for price, gain, pct in ((12.0, 200, 20), (9.0, -100, -10), (10.0, 0, 0)):
        holding = build_holding([ORDER], [], price, TODAY)
        assert (holding["gain"], holding["gain_pct"]) == (gain, pct)
    # An awkward price must not show a loss of paise on day one.
    assert build_holding([{**ORDER, "price_at_order": 2517.3}], [], 2517.3, TODAY)["gain"] == 0


def test_sip_counts_only_instalments_already_due_and_priced() -> None:
    # 10 Oct falls on a closed day: bought at the next price. 10 Nov at 20.
    series = [(date(2026, 10, 9), 5.0), (date(2026, 10, 12), 10.0), (date(2026, 11, 10), 20.0)]
    holding = build_holding([SIP], series, 20.0, TODAY)
    assert (holding["invested"], holding["current_value"]) == (1000, 1500)  # 50 + 25 units
    assert build_holding([SIP], series[:2], 10.0, TODAY)["invested"] == 500
    future = {**SIP, "next_installment_date": "2026-12-10"}
    assert build_holding([future], series, 20.0, TODAY) is None
    assert build_holding([ORDER, future], series, 20.0, TODAY)["invested"] == 1000


def test_unknown_price_or_units_gives_no_value() -> None:
    assert build_holding([ORDER], [], None, TODAY)["current_value"] is None
    assert build_holding([{**ORDER, "price_at_order": None}], [], 10.0, TODAY)["gain"] is None


async def test_portfolio_groups_and_keeps_unvalued_out_of_totals(mongo_test_db, monkeypatch) -> None:
    await get_investments_collection().insert_many(
        [
            {**ORDER, "created_at": datetime.now(UTC)},
            {**ORDER, "created_at": datetime.now(UTC)},
            {**ORDER, "created_at": datetime.now(UTC), "instrument_id": "mf-2"},
            {**ORDER, "created_at": datetime.now(UTC), "status": "failed"},
            {**ORDER, "created_at": datetime.now(UTC), "user_id": "other"},
        ]
    )

    async def prices(instrument_id):
        if instrument_id == "mf-2":
            raise DataProviderError("down")
        return [], 11.0

    monkeypatch.setattr(portfolio_service, "get_prices", prices)
    p = await get_portfolio("u", TODAY)
    assert (p["invested"], p["current_value"], p["gain"], p["gain_pct"]) == (2000, 2200, 200, 10)
    assert p["unvalued_count"] == 1 and len(p["holdings"]) == 2
    assert (await get_portfolio("nobody", TODAY))["gain_pct"] is None


async def test_listed_sip_shows_its_upcoming_date(mongo_test_db) -> None:
    await get_investments_collection().insert_one({**SIP, "created_at": datetime.now(UTC)})
    upcoming = (await list_investments("u"))[0]["next_installment_date"]
    assert upcoming > date.today().isoformat() and upcoming.endswith("-10")  # noqa: DTZ011


def test_portfolio_route(client, auth_headers) -> None:
    assert client.get("/api/v1/investments/portfolio").status_code == 401
    body = client.get("/api/v1/investments/portfolio", headers=auth_headers).json()
    assert body["holdings"] == [] and body["invested"] == 0


def _article(url: str, tickers=(), sectors=()) -> dict:
    record = {"url": url, "title": url, "source": "S", "published_at": datetime.now(UTC) - timedelta(hours=1)}
    return {**record, "tickers": list(tickers)} | ({"sectors": list(sectors)} if sectors else {})


async def test_sector_news_prefers_sector_stories_and_skips_the_stock(mongo_test_db) -> None:
    assert set(SECTOR_NEWS_QUERIES) == set(SECTORS)
    await upsert_news_articles(
        [
            _article("sector", sectors=["it"]),
            _article("sector-about-tcs", ["TCS.NS"], ["it"]),
            _article("infy", ["INFY.NS"]),
            _article("bank", ["SBIN.NS"]),
        ]
    )
    # A second search finding the same story adds its tag.
    await upsert_news_articles([_article("sector", sectors=["banking"])])
    stored = await get_news_collection().find_one({"url": "sector"})
    assert sorted(stored["sectors"]) == ["banking", "it"]

    assert {a["url"] for a in await sector_news("it", "TCS.NS")} == {"sector", "infy"}
    assert {a["url"] for a in await sector_news("it", limit=2)} == {"sector", "sector-about-tcs"}
    assert await sector_news("nope") is None


def test_sector_news_route(client, auth_headers) -> None:
    assert client.get("/api/v1/sectors/it/news", headers=auth_headers).json() == []
    assert client.get("/api/v1/sectors/nope/news", headers=auth_headers).status_code == 404


def test_sector_headlines_must_name_the_sector() -> None:
    assert is_sector_headline("pharma", "Size of India's pharma sector may double")
    assert is_sector_headline("it", "Indian IT stocks gain") and is_sector_headline("banking", "Bank stocks regain appeal")
    for sector, title in (
        ("pharma", "Sensex gains 510 points"),
        ("it", "Why it may be time to sell"),
        ("auto", "Canadian auto sector moves away from U.S. imports"),
        ("pharma", "Marksans Pharma Share Price Target 2026"),
        ("auto", "Auto \u0936\u0947\u092f\u0930"),
    ):
        assert not is_sector_headline(sector, title)
