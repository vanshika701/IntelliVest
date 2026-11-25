"""Trading dates, catch-up, quotes and fund sizes."""

from datetime import UTC, date, datetime

import pandas as pd

from app.data.collections import get_prices_collection
from app.services import fund_aum_provider, instrument_service, market_data_service, quote_service
from app.services.market_data_service import IST, catch_up, clean_history, last_final_weekday
from app.services.price_date_migration import migrate_price_dates


def _history(*days: str) -> pd.DataFrame:
    n = len(days)
    columns = {c: [1.0] * n for c in ("Open", "High", "Low", "Close")}
    return pd.DataFrame({**columns, "Volume": [1] * n}, index=pd.DatetimeIndex(days, tz="Asia/Kolkata"))


def test_trading_day_is_kept_and_unfinished_day_dropped() -> None:
    history = _history("2026-11-23", "2026-11-25")
    during = datetime(2026, 11, 25, 12, 0, tzinfo=IST)
    assert [r["date"] for r in clean_history("T", history, during)] == [datetime(2026, 11, 23, tzinfo=UTC)]
    after = datetime(2026, 11, 25, 16, 0, tzinfo=IST)
    assert clean_history("T", history, after)[-1]["date"] == datetime(2026, 11, 25, tzinfo=UTC)


def test_last_final_weekday() -> None:
    assert last_final_weekday(datetime(2026, 11, 25, 15, 0, tzinfo=IST)) == date(2026, 11, 24)
    assert last_final_weekday(datetime(2026, 11, 25, 16, 0, tzinfo=IST)) == date(2026, 11, 25)
    assert last_final_weekday(datetime(2026, 11, 23, 9, 0, tzinfo=IST)) == date(2026, 11, 20)  # Monday


async def test_migration_moves_each_old_row_once(mongo_test_db) -> None:
    prices = get_prices_collection()
    old = [{"ticker": "T", "date": datetime(2026, 11, d, tzinfo=UTC), "close": d} for d in (17, 18, 19, 22)]
    # Ingested after the fix: already right, and the old row for that day goes.
    new = {"ticker": "T", "date": datetime(2026, 11, 23, tzinfo=UTC), "close": 99, "date_basis": "exchange"}
    await prices.insert_many([*old, new])
    assert await migrate_price_dates() == 4
    assert await migrate_price_dates() == 0
    rows = [(r["date"].day, r["close"]) async for r in prices.find().sort("date", 1)]
    assert rows == [(18, 17), (19, 18), (20, 19), (23, 99)]


async def test_catch_up_only_when_behind_and_not_repeatedly(mongo_test_db, monkeypatch) -> None:
    runs = []

    async def ingest(tickers):
        runs.append(tickers)

    monkeypatch.setattr(market_data_service, "ingest_stock_universe", ingest)
    monkeypatch.setattr(market_data_service, "_last_catch_up", None)
    now = datetime(2026, 11, 25, 20, 0, tzinfo=IST)
    row = {"ticker": "T", "date": datetime(2026, 11, 23, tzinfo=UTC), "close": 1, "date_basis": "exchange"}
    await get_prices_collection().insert_one(row)
    assert await catch_up(["T"], now) and not await catch_up(["T"], now)
    assert await catch_up(["T"], datetime(2026, 11, 25, 23, 30, tzinfo=IST))
    await get_prices_collection().update_one({"ticker": "T"}, {"$set": {"date": datetime(2026, 11, 25, tzinfo=UTC)}})
    assert not await catch_up(["T"], datetime(2026, 11, 26, 9, 0, tzinfo=IST))
    assert len(runs) == 2


BARS = {
    "intraday": [(datetime(2026, 11, 23, 15, 25, tzinfo=IST), 99.0), (datetime(2026, 11, 25, 11, 55, tzinfo=IST), 110.0)],
    "daily": [(datetime(2026, 11, 23, tzinfo=IST), 100.0)],
}


def test_quote_market_state() -> None:
    quote = quote_service.build_quote(BARS, datetime(2026, 11, 25, 12, 0, tzinfo=IST))
    assert quote["market_open"] and quote["change_pct"] == 10 and quote["date"] == date(2026, 11, 25)
    assert not quote_service.build_quote(BARS, datetime(2026, 11, 26, 12, 0, tzinfo=IST))["market_open"]
    assert quote_service.build_quote(BARS | {"daily": []}, datetime.now(IST))["previous_close"] == 99
    assert quote_service.build_quote({"intraday": [], "daily": []}, datetime.now(IST)) is None


async def test_instrument_uses_quote_and_survives_failure(mongo_test_db, monkeypatch) -> None:
    await get_prices_collection().insert_one({"ticker": "TCS.NS", "date": datetime(2026, 11, 23, tzinfo=UTC), "close": 100.0})
    monkeypatch.setattr(quote_service, "_download", lambda: {"TCS.NS": BARS})
    item = await instrument_service.get_instrument("stock-TCS.NS")
    assert (item["price"], item["day_change"], item["price_date"]) == (110, 10, date(2026, 11, 25))
    assert item["quote_delay_minutes"] == 15

    def broken():
        raise RuntimeError("down")

    quote_service._cache.clear()
    monkeypatch.setattr(quote_service, "_download", broken)
    item = await instrument_service.get_instrument("stock-TCS.NS")
    assert item["price"] == 100 and item["quote_fetched_at"] is None


def _scheme(code: int, name: str, lakhs: float, fof: float = 0) -> dict:
    return {"AMFI_Code": code, "SchemeNAVName": name, "AverageAumForTheMonth": {"a": lakhs, "b": fof}}


async def test_fund_size_adds_up_plans_in_crore(monkeypatch) -> None:
    payload = {
        "selectedPeriod": "July - September 2026",
        "data": [{"schemes": [
            _scheme(1, "X Large Cap FUND-DIRECT PLAN -GROWTH", 1000),
            _scheme(2, "X Large Cap Fund - Regular Plan - IDCW", 500),
            _scheme(3, "X Dividend Yield Fund - Direct Plan", 0, 70),
            _scheme(4, "X Closed Fund - Direct Plan", 0),
        ]}],
    }  # fmt: skip

    async def fetch():
        return payload

    monkeypatch.setattr(fund_aum_provider, "_fetch", fetch)
    size = {"aum_crore": 15.0, "aum_period": "July - September 2026"}
    assert await fund_aum_provider.get_aum(1) == await fund_aum_provider.get_aum(2) == size
    assert (await fund_aum_provider.get_aum(3))["aum_crore"] == 0.7
    assert await fund_aum_provider.get_aum(4) == {} == await fund_aum_provider.get_aum(9)


async def test_fund_size_failure_is_blank(monkeypatch) -> None:
    async def fetch():
        return {"unexpected": 1}

    monkeypatch.setattr(fund_aum_provider, "_fetch", fetch)
    assert await fund_aum_provider.get_aum(1) == {}
