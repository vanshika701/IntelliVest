"""Phase 7 market statistics: maths on synthetic prices (pure), storage
and the route."""

from datetime import UTC, datetime, timedelta

import numpy as np
import pytest
from fastapi.testclient import TestClient

from app.core.constants import STOCK_UNIVERSE
from app.data.collections import get_market_stats_collection, get_prices_collection
from app.services.market_stats import (
    LOOKBACK_RETURNS,
    MIN_RETURNS,
    STALE_AFTER_DAYS,
    TRADING_DAYS_PER_YEAR,
    compute_market_stats,
    max_drawdown,
)
from app.services.market_stats_service import refresh_market_stats

NOW = datetime(2026, 11, 20, tzinfo=UTC)
END = datetime(2026, 11, 20)  # noqa: DTZ001 — MongoDB returns price dates as naive UTC


def rows_from_returns(returns: np.ndarray, end: datetime = END, start_price: float = 100.0):
    closes = start_price * np.cumprod(np.concatenate([[1.0], 1 + returns]))
    return [
        {"date": end - timedelta(days=len(closes) - 1 - i), "close": float(c)}
        for i, c in enumerate(closes)
    ]


def random_returns(seed: int, n: int = 400, daily_vol: float = 0.01) -> np.ndarray:
    return np.random.default_rng(seed).normal(0.0, daily_vol, n)


def test_max_drawdown() -> None:
    # Prices 100 -> 120 -> 90 -> 130: worst fall is 120 -> 90.
    assert max_drawdown(np.array([0.2, -0.25, 130 / 90 - 1])) == pytest.approx(-0.25)
    assert max_drawdown(np.array([0.1, 0.1])) == 0


def test_corporate_action_jumps_are_dropped() -> None:
    a_returns, b_returns = random_returns(1), random_returns(2)
    a_returns[200] = -0.40  # e.g. a demerger the price history wasn't adjusted for
    stats = compute_market_stats(
        {"A": rows_from_returns(a_returns), "B": rows_from_returns(b_returns)}, NOW
    )
    assert stats["observations"] == 399  # that day removed for both stocks
    assert [(b["ticker"], b["daily_return"]) for b in stats["data_breaks"]] == [("A", -0.4)]
    assert stats["stocks"]["A"]["max_drawdown"] == pytest.approx(
        max_drawdown(np.delete(a_returns, 200)), abs=1e-6
    )
    assert stats["stocks"]["A"]["sample_annual_volatility"] == pytest.approx(
        0.01 * np.sqrt(TRADING_DAYS_PER_YEAR), rel=0.1
    )


def test_needs_two_usable_stocks() -> None:
    assert compute_market_stats({"A": rows_from_returns(random_returns(1))}, NOW) is None
    assert compute_market_stats({}, NOW) is None


def test_volatility_is_annualised() -> None:
    stats = compute_market_stats(
        {"A": rows_from_returns(random_returns(1, daily_vol=0.01)),
         "B": rows_from_returns(random_returns(2, daily_vol=0.02))},
        NOW,
    )
    a, b = stats["stocks"]["A"], stats["stocks"]["B"]
    # Sample volatility is unshrunk, so it should be close to the true value.
    assert a["sample_annual_volatility"] == pytest.approx(0.01 * np.sqrt(TRADING_DAYS_PER_YEAR), rel=0.1)
    assert b["sample_annual_volatility"] == pytest.approx(0.02 * np.sqrt(TRADING_DAYS_PER_YEAR), rel=0.1)
    assert b["annual_volatility"] > a["annual_volatility"]
    assert stats["observations"] == 400
    assert stats["as_of"] == END


def test_correlation_reflects_how_stocks_move_together() -> None:
    base = random_returns(1)
    stats = compute_market_stats(
        {"A": rows_from_returns(base),
         "TWIN": rows_from_returns(base * 1.5),  # same moves, bigger
         "OTHER": rows_from_returns(random_returns(99))},
        NOW,
    )
    corr = stats["correlation"]
    assert corr["A"]["A"] == pytest.approx(1)
    assert corr["A"]["TWIN"] > 0.8  # shrinkage pulls it below 1, but it stays high
    assert abs(corr["A"]["OTHER"]) < 0.2
    assert corr["A"]["OTHER"] == corr["OTHER"]["A"]
    assert 0 <= stats["shrinkage"] <= 1


def test_diversification_lowers_volatility() -> None:
    series = {f"S{i}": rows_from_returns(random_returns(i)) for i in range(5)}
    stats = compute_market_stats(series, NOW)
    assert stats["equal_weight_volatility"] < stats["average_stock_volatility"]


def test_covariance_is_usable_by_an_optimizer() -> None:
    series = {f"S{i}": rows_from_returns(random_returns(i)) for i in range(6)}
    stats = compute_market_stats(series, NOW)
    cov = np.array([[stats["covariance"][a][b] for b in stats["tickers"]] for a in stats["tickers"]])
    assert np.allclose(cov, cov.T)
    assert np.linalg.eigvalsh(cov).min() > 0  # positive definite


def test_excludes_stale_and_short_series() -> None:
    stale_end = END - timedelta(days=STALE_AFTER_DAYS + 1)
    stats = compute_market_stats(
        {"A": rows_from_returns(random_returns(1)),
         "B": rows_from_returns(random_returns(2)),
         "STALE": rows_from_returns(random_returns(3), end=stale_end),
         "SHORT": rows_from_returns(random_returns(4, n=MIN_RETURNS - 10)),
         "EMPTY": []},
        NOW,
    )
    assert stats["tickers"] == ["A", "B"]
    assert {e["ticker"] for e in stats["excluded"]} == {"STALE", "SHORT", "EMPTY"}


def test_aligns_on_shared_dates_and_caps_the_lookback() -> None:
    long = rows_from_returns(random_returns(1, n=LOOKBACK_RETURNS + 100))
    gappy = rows_from_returns(random_returns(2, n=LOOKBACK_RETURNS + 100))
    del gappy[-10]  # a day B didn't trade
    stats = compute_market_stats({"A": long, "B": gappy}, NOW)
    assert stats["observations"] == LOOKBACK_RETURNS
    shared = {r["date"] for r in long} & {r["date"] for r in gappy}
    assert stats["start"] == sorted(shared)[-(LOOKBACK_RETURNS + 1)]


# --- Storage and route ------------------------------------------------------

async def _store_prices(tickers: list[str]) -> None:
    docs = []
    for i, ticker in enumerate(tickers):
        for row in rows_from_returns(random_returns(i)):
            docs.append({"ticker": ticker, **row})
    await get_prices_collection().insert_many(docs)


async def test_refresh_stores_one_document_per_price_date(mongo_test_db) -> None:
    await _store_prices(STOCK_UNIVERSE[:4])
    first = await refresh_market_stats(NOW)
    assert first["tickers"] == sorted(STOCK_UNIVERSE[:4])
    assert {e["reason"] for e in first["excluded"]} == {"no prices stored"}

    await refresh_market_stats(NOW)  # same prices again
    assert await get_market_stats_collection().count_documents({}) == 1


async def test_refresh_without_prices_stores_nothing(mongo_test_db) -> None:
    assert await refresh_market_stats(NOW) is None
    assert await get_market_stats_collection().count_documents({}) == 0


def test_latest_route(client: TestClient, auth_headers: dict[str, str]) -> None:
    assert client.get("/api/v1/market-stats/latest").status_code == 401
    assert client.get("/api/v1/market-stats/latest", headers=auth_headers).status_code == 404
