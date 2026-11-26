"""Instrument search/detail/history tests. mfapi.in and yfinance are
replaced with fakes — these test our parsing, ranking and API contract,
not the providers."""

from datetime import UTC, date, datetime

import pytest
from fastapi.testclient import TestClient

from app.core.cache import MISSING, TTLCache
from app.data.collections import get_prices_collection
from app.services import instrument_service, mfapi_client
from app.services.instrument_service import (
    InstrumentNotFound,
    classify_scheme,
    get_instrument,
    parse_instrument_id,
)

ISIN = {"isinGrowth": "INF000000001", "isinDivReinvestment": None}
SCHEME_LIST_PAYLOAD = [
    {"schemeCode": 1, "schemeName": "SBI Gold Fund - Regular Plan - IDCW", **ISIN},
    {"schemeCode": 2, "schemeName": "SBI Gold Fund - Direct Plan - Growth", **ISIN},
    {"schemeCode": 3, "schemeName": "Edelweiss Gold ETF", **ISIN},
    {"schemeCode": 4, "schemeName": "HSBC Gold ETF Fund of Fund - Direct Plan - Growth", **ISIN},
    {"schemeCode": 5, "schemeName": "Gold Benchmark Exchange Traded Scheme", "isinGrowth": None, "isinDivReinvestment": None},
    {"schemeCode": 6, "schemeName": "Axis Bluechip Fund - Direct Plan - Growth", **ISIN},
]
SEARCH_PAYLOAD = [{"schemeCode": 3, "schemeName": "Edelweiss Gold ETF"}]

SCHEME_PAYLOAD = {
    "meta": {"fund_house": "SBI Mutual Fund", "scheme_category": "FoF Domestic", "scheme_name": "SBI Gold Fund - Direct Plan - Growth"},
    "data": [
        {"date": "20-11-2026", "nav": "30.00"},
        {"date": "19-11-2026", "nav": "29.40"},
        {"date": "18-11-2026", "nav": "bad"},
        {"date": "17-11-2026", "nav": "29.00"},
    ],
}


@pytest.fixture(autouse=True)
def _fresh_caches():
    mfapi_client._search_cache.clear()
    mfapi_client._scheme_list_cache.clear()
    mfapi_client._scheme_cache.clear()
    instrument_service._intraday_cache.clear()


@pytest.fixture
def fake_mfapi(monkeypatch: pytest.MonkeyPatch):
    async def fake_get_json(path: str, params: dict | None = None):
        if path == "/mf":
            return SCHEME_LIST_PAYLOAD
        if path == "/mf/search":
            return SEARCH_PAYLOAD
        if path == "/mf/2":
            return SCHEME_PAYLOAD
        return {"meta": {}, "data": [], "status": "FAIL"}

    monkeypatch.setattr(mfapi_client, "_get_json", fake_get_json)


@pytest.fixture
def broken_mfapi(monkeypatch: pytest.MonkeyPatch):
    async def failing_get_json(path: str, params: dict | None = None):
        raise TimeoutError("provider timed out")

    monkeypatch.setattr(mfapi_client, "_get_json", failing_get_json)


def test_ttl_cache_expires_entries(monkeypatch: pytest.MonkeyPatch) -> None:
    clock = [100.0]
    monkeypatch.setattr("app.core.cache.time.monotonic", lambda: clock[0])
    cache = TTLCache(ttl_seconds=10, max_items=2)
    cache.set("a", 1)
    assert cache.get("a") == 1
    clock[0] += 11
    assert cache.get("a") is MISSING


def test_ttl_cache_evicts_oldest_when_full() -> None:
    cache = TTLCache(ttl_seconds=60, max_items=2)
    cache.set("a", 1)
    cache.set("b", 2)
    cache.set("c", 3)
    assert cache.get("a") is MISSING
    assert cache.get("c") == 3


def test_parse_navs_sorts_oldest_first_and_skips_bad_rows() -> None:
    navs = mfapi_client.parse_navs(SCHEME_PAYLOAD["data"])
    assert navs == [(date(2026, 11, 17), 29.0), (date(2026, 11, 19), 29.4), (date(2026, 11, 20), 30.0)]


def test_classify_scheme_separates_etfs_from_fund_of_funds() -> None:
    assert classify_scheme("Edelweiss Gold ETF") == "ETF"
    assert classify_scheme("Gold Benchmark Exchange Traded Scheme (Gold BeES)") == "ETF"
    assert classify_scheme("HSBC Gold ETF Fund of Fund - Direct Plan") == "MF"
    assert classify_scheme("SBI Gold Fund - Direct Plan - Growth") == "MF"


def test_parse_instrument_id_rejects_unknown_ids() -> None:
    assert parse_instrument_id("stock-TCS.NS") == ("stock", "TCS.NS")
    assert parse_instrument_id("mf-111954") == ("mf", "111954")
    for bad in ("stock-NOTREAL.NS", "mf-abc", "bond-1", ""):
        with pytest.raises(InstrumentNotFound):
            parse_instrument_id(bad)


async def test_mf_detail_computes_day_change_and_placeholder_stats(fake_mfapi) -> None:
    detail = await get_instrument("mf-2")
    assert detail["type"] == "MF"
    assert detail["price"] == 30.0
    assert detail["day_change"] == pytest.approx(0.6)
    assert detail["day_change_pct"] == pytest.approx(0.6 / 29.4 * 100, rel=1e-3)
    assert detail["supports_intraday"] is False
    assert detail["stats"]["rating"] is None
    assert "min_sip" in detail["stats"]["placeholder_fields"]


async def test_stock_detail_reads_stored_prices(mongo_test_db) -> None:
    await get_prices_collection().insert_many(
        [
            {"ticker": "TCS.NS", "date": datetime(2026, 11, 19, tzinfo=UTC), "close": 100.0},
            {"ticker": "TCS.NS", "date": datetime(2026, 11, 20, tzinfo=UTC), "close": 95.0},
        ]
    )
    detail = await get_instrument("stock-TCS.NS")
    assert detail["type"] == "STOCK"
    assert detail["day_change"] == pytest.approx(-5.0)
    assert detail["day_change_pct"] == pytest.approx(-5.0)
    # Minimum = one share; derived, so not flagged as a placeholder.
    assert detail["stats"]["min_investment"] == 95
    assert detail["stats"]["placeholder_fields"] == []


def test_search_shows_one_best_variant_per_fund_and_tags_types(
    client: TestClient, auth_headers: dict[str, str], fake_mfapi
) -> None:
    response = client.get("/api/v1/instruments/search?q=gold", headers=auth_headers)
    assert response.status_code == 200
    body = response.json()
    assert body["partial"] is False
    # NSE companies with "gold" in their name come first, at most 5.
    stocks = [r for r in body["results"] if r["type"] == "STOCK"]
    assert 0 < len(stocks) <= 5 and body["results"][: len(stocks)] == stocks
    types = {r["name"]: r["type"] for r in body["results"] if r["type"] != "STOCK"}
    # Direct Growth wins over Regular IDCW; closed (no-ISIN) schemes and
    # non-matching funds are excluded.
    assert types == {
        "SBI Gold Fund - Direct Plan - Growth": "MF",
        "Edelweiss Gold ETF": "ETF",
        "HSBC Gold ETF Fund of Fund - Direct Plan - Growth": "MF",
    }


def test_match_schemes_requires_every_word() -> None:
    schemes = mfapi_client._to_schemes(SCHEME_LIST_PAYLOAD)
    assert [s["scheme_code"] for s in mfapi_client.match_schemes(schemes, "sbi gold")] == [1, 2]


def test_search_falls_back_to_search_endpoint_when_list_fails(
    client: TestClient, auth_headers: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    async def fake_get_json(path: str, params: dict | None = None):
        if path == "/mf":
            raise TimeoutError("list too slow")
        return SEARCH_PAYLOAD

    monkeypatch.setattr(mfapi_client, "_get_json", fake_get_json)
    body = client.get("/api/v1/instruments/search?q=gold", headers=auth_headers).json()
    assert [r["name"] for r in body["results"] if r["type"] != "STOCK"] == ["Edelweiss Gold ETF"]
    assert body["partial"] is False


def test_search_includes_tracked_stocks(client: TestClient, auth_headers: dict[str, str], fake_mfapi) -> None:
    body = client.get("/api/v1/instruments/search?q=infosys", headers=auth_headers).json()
    assert body["results"][0] == {
        "id": "stock-INFY.NS",
        "name": "Infosys",
        "type": "STOCK",
        "symbol": "INFY.NS",
        "subtitle": "NSE · INFY.NS",
    }


def test_search_degrades_to_partial_when_fund_provider_fails(
    client: TestClient, auth_headers: dict[str, str], broken_mfapi
) -> None:
    body = client.get("/api/v1/instruments/search?q=tata", headers=auth_headers).json()
    assert body["partial"] is True
    # Only stocks; the two tracked Tata companies first.
    assert {r["type"] for r in body["results"]} == {"STOCK"}
    assert [r["id"] for r in body["results"][:2]] == ["stock-TCS.NS", "stock-TMPV.NS"]


def test_search_validates_query_length(client: TestClient, auth_headers: dict[str, str]) -> None:
    assert client.get("/api/v1/instruments/search?q=g", headers=auth_headers).status_code == 422


def test_search_requires_auth(client: TestClient) -> None:
    assert client.get("/api/v1/instruments/search?q=gold").status_code == 401


def test_detail_unknown_instrument_is_404(client: TestClient, auth_headers: dict[str, str], fake_mfapi) -> None:
    assert client.get("/api/v1/instruments/mf-999", headers=auth_headers).status_code == 404
    assert client.get("/api/v1/instruments/stock-FAKE.NS", headers=auth_headers).status_code == 404


def test_detail_provider_failure_is_502(client: TestClient, auth_headers: dict[str, str], broken_mfapi) -> None:
    assert client.get("/api/v1/instruments/mf-2", headers=auth_headers).status_code == 502


def test_history_returns_daily_points(client: TestClient, auth_headers: dict[str, str], fake_mfapi) -> None:
    body = client.get("/api/v1/instruments/mf-2/history", headers=auth_headers).json()
    assert body["interval"] == "1d"
    assert body["points"][-1] == {"t": "2026-11-20", "v": 30.0}


def test_intraday_is_empty_for_funds(client: TestClient, auth_headers: dict[str, str], fake_mfapi) -> None:
    body = client.get("/api/v1/instruments/mf-2/intraday", headers=auth_headers).json()
    assert body == {"interval": "5m", "points": []}


def test_intraday_for_stock_is_cached(
    client: TestClient, auth_headers: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = []

    def fake_fetch(ticker: str) -> list[dict]:
        calls.append(ticker)
        return [{"t": "2026-11-20T04:00:00+00:00", "v": 100.0}]

    monkeypatch.setattr(instrument_service, "_fetch_intraday", fake_fetch)
    for _ in range(2):
        body = client.get("/api/v1/instruments/stock-TCS.NS/intraday", headers=auth_headers).json()
        assert body["points"] == [{"t": "2026-11-20T04:00:00+00:00", "v": 100.0}]
    assert calls == ["TCS.NS"]
