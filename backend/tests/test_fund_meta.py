"""Live instrument metadata: caching, failure handling, unrated funds."""

from app.services import fund_meta_provider as meta


def test_zero_stars_means_unrated() -> None:
    assert meta.stars(0) is None and meta.stars(None) is None
    assert meta.stars(4) == 4


async def test_fund_rating_is_looked_up_by_isin_and_cached(monkeypatch) -> None:
    calls = []

    def fake(isin):
        calls.append(isin)
        return {"rating": 5.0, "rating_source": "Morningstar via Yahoo Finance"}

    monkeypatch.setattr(meta, "_fetch_fund", fake)
    for _ in range(2):
        result = await meta.get_meta("MF", 10.0, isin="INF1")
    assert result["rating"] == 5 and calls == ["INF1"]
    assert result["aum_crore"] is None and "min_sip" in result["placeholder_fields"]
    assert (await meta.get_meta("MF", 10.0))["rating"] is None  # no ISIN, no lookup


async def test_stock_values_and_provider_failure(monkeypatch) -> None:
    monkeypatch.setattr(meta, "_fetch_stock", lambda _t: {"market_cap_crore": 100.0, "analyst_rating": "Buy"})
    result = await meta.get_meta("STOCK", 95.0, ticker="TCS.NS")
    assert result["market_cap_crore"] == 100 and result["analyst_rating"] == "Buy"

    def broken(_t):
        raise RuntimeError("down")

    monkeypatch.setattr(meta, "_fetch_stock", broken)
    result = await meta.get_meta("STOCK", 95.0, ticker="INFY.NS")
    assert result["market_cap_crore"] is None and result["min_sip"] == 95
