"""Phase 7 equity optimizer on synthetic statistics with known answers."""

from datetime import datetime

import numpy as np
import pytest

from app.core.constants import STOCK_UNIVERSE, TICKER_TO_SECTOR
from app.core.portfolio_config import (
    MAX_SECTOR_WEIGHT,
    MAX_STOCK_WEIGHT,
    MIN_HOLDING_WEIGHT,
    SENTIMENT_MAX_VARIANCE_INCREASE,
    SENTIMENT_MAX_WEIGHT_SHIFT,
)
from app.services.equity_optimizer import OptimizationError, optimize_equity

AS_OF = datetime(2026, 11, 20)  # noqa: DTZ001 — matches stored naive UTC dates


def make_stats(tickers: list[str], vols: list[float], corr: float = 0.3) -> dict:
    vols_arr = np.array(vols)
    correlation = np.full((len(tickers), len(tickers)), corr)
    np.fill_diagonal(correlation, 1.0)
    cov = correlation * np.outer(vols_arr, vols_arr)
    return {
        "tickers": tickers,
        "covariance": {a: {b: float(cov[i, j]) for j, b in enumerate(tickers)} for i, a in enumerate(tickers)},
        "stocks": {t: {"annual_volatility": v} for t, v in zip(tickers, vols, strict=True)},
        "as_of": AS_OF,
    }


def universe_stats(seed: int = 0) -> dict:
    vols = np.random.default_rng(seed).uniform(0.15, 0.40, len(STOCK_UNIVERSE))
    return make_stats(list(STOCK_UNIVERSE), list(vols))


def weights(result: dict) -> dict[str, float]:
    return {s["ticker"]: s["weight"] for s in result["stocks"]}


def assert_valid(result: dict) -> None:
    w = weights(result)
    assert sum(w.values()) == pytest.approx(1, abs=1e-3)
    assert all(0 <= v <= MAX_STOCK_WEIGHT + 1e-3 for v in w.values())
    assert all(v == 0 or v >= MIN_HOLDING_WEIGHT - 1e-3 for v in w.values())
    sectors: dict[str, float] = {}
    for ticker, v in w.items():
        sectors[TICKER_TO_SECTOR[ticker]] = sectors.get(TICKER_TO_SECTOR[ticker], 0) + v
    assert max(sectors.values()) <= MAX_SECTOR_WEIGHT + 1e-3


@pytest.mark.parametrize("seed", range(5))
def test_limits_always_hold(seed: int) -> None:
    result = optimize_equity(universe_stats(seed), use_sentiment=False)
    assert_valid(result)
    assert result["portfolio"]["holdings"] >= 7  # forced by the 15% cap


@pytest.mark.parametrize("seed", range(5))
def test_never_riskier_than_equal_weight(seed: int) -> None:
    result = optimize_equity(universe_stats(seed), use_sentiment=False)
    assert result["portfolio"]["annual_volatility"] <= result["equal_weight"]["annual_volatility"]


def test_prefers_calmer_stocks() -> None:
    stats = universe_stats(3)
    w = weights(optimize_equity(stats, use_sentiment=False))
    calmest = min(STOCK_UNIVERSE, key=lambda t: stats["stocks"][t]["annual_volatility"])
    wildest = max(STOCK_UNIVERSE, key=lambda t: stats["stocks"][t]["annual_volatility"])
    assert w[calmest] > w[wildest]


def test_identical_stocks_without_caps_split_evenly() -> None:
    tickers = ["TCS.NS", "HDFCBANK.NS", "ITC.NS", "SUNPHARMA.NS"]
    result = optimize_equity(make_stats(tickers, [0.2] * 4), use_sentiment=False,
                             max_stock=1.0, max_sector=1.0)
    assert all(v == pytest.approx(0.25, abs=1e-3) for v in weights(result).values())


def test_sentiment_tilts_within_its_budget() -> None:
    stats = universe_stats(1)
    plain = optimize_equity(stats, use_sentiment=False)
    held = [s["ticker"] for s in plain["stocks"] if s["weight"] > 0]
    favourite, disliked = held[-1], held[0]
    signals = {
        favourite: {"sentiment_score": 0.8, "article_count": 10},
        disliked: {"sentiment_score": -0.8, "article_count": 10},
    }
    tilted = optimize_equity(stats, signals)
    assert_valid(tilted)
    assert tilted["sentiment_used"] is True
    before, after = weights(plain), weights(tilted)
    assert after[favourite] > before[favourite]
    assert after[disliked] < before[disliked]
    assert all(abs(after[t] - before[t]) <= SENTIMENT_MAX_WEIGHT_SHIFT + 1e-3 for t in after)
    variance_ratio = (tilted["portfolio"]["annual_volatility"] / plain["portfolio"]["annual_volatility"]) ** 2
    assert variance_ratio <= 1 + SENTIMENT_MAX_VARIANCE_INCREASE + 1e-3
    # A stock the risk step left out is not brought back by good news.
    dropped = [t for t, v in before.items() if v == 0]
    if dropped:
        boosted = optimize_equity(stats, {dropped[0]: {"sentiment_score": 1, "article_count": 50}})
        assert weights(boosted)[dropped[0]] == 0


def test_thin_news_is_ignored() -> None:
    stats = universe_stats(2)
    plain = optimize_equity(stats, use_sentiment=False)
    thin = optimize_equity(stats, {STOCK_UNIVERSE[0]: {"sentiment_score": 0.9, "article_count": 2}})
    assert thin["sentiment_used"] is False
    assert weights(thin) == weights(plain)


def test_impossible_limits_are_reported() -> None:
    tickers = ["TCS.NS", "INFY.NS", "WIPRO.NS"]  # one sector, capped at 35%
    with pytest.raises(OptimizationError, match="at most 35%"):
        optimize_equity(make_stats(tickers, [0.2, 0.25, 0.3]), use_sentiment=False)
