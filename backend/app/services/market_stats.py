"""Pure Phase 7 market statistics: per-stock return and risk, and how the
stocks move together, from stored daily closes. No I/O; the async
service in market_stats_service.py loads prices and stores the result.

Why each number is computed the way it is:
- Daily SIMPLE returns (close_t / close_t-1 - 1), aligned on the dates
  every included stock traded, so each row compares the same day.
- Annualised with 252 trading days: volatility scales with sqrt(252),
  mean return with 252.
- The covariance matrix is Ledoit-Wolf shrunk. With ~500 days and 20
  stocks the plain sample covariance is noisy, and an optimizer
  (step 4) exploits that noise: it piles into pairs that only LOOK
  unrelated by chance. Shrinkage pulls the estimate towards a simple,
  stable target by an amount estimated from the data itself.
  Ledoit & Wolf (2004), "A well-conditioned estimator for large-dimensional
  covariance matrices", J. Multivariate Analysis 88(2).
- A daily move bigger than MAX_PLAUSIBLE_DAILY_MOVE is treated as a data
  break, not a real return, and that day is dropped for every stock. These
  come from unadjusted corporate actions: TMPV.NS "falls" 40% on
  2025-10-13, the Tata Motors demerger, when shareholders actually
  received shares in the separated company. Kept in, one such day dominates
  that stock's volatility and drawdown.
- Mean returns are reported but NOT trusted: two years of history says
  very little about future returns, so step 4 does not optimise for them.
"""

from datetime import date, datetime, timedelta

import numpy as np
from sklearn.covariance import LedoitWolf

MARKET_STATS_VERSION = "mstats-v1"
TRADING_DAYS_PER_YEAR = 252
LOOKBACK_RETURNS = 504  # about two trading years
MIN_RETURNS = 250  # about one trading year; fewer is too little to estimate risk
STALE_AFTER_DAYS = 7  # same rule as Phase 6 sectors
# Larger daily moves are data breaks. Checked on 2012-2026 Yahoo prices for
# the 20 tracked stocks: the biggest genuine one-day moves were Axis Bank
# -27.9% (2020-03-23, COVID crash) and SBI +27.7% (2017-10-25, bank
# recapitalisation news); the only larger move was the TMPV demerger break
# (-40%). 35% keeps every real move and still catches that break.
MAX_PLAUSIBLE_DAILY_MOVE = 0.35


def _day(value: datetime | date) -> date:
    return value.date() if isinstance(value, datetime) else value


def max_drawdown(returns: np.ndarray) -> float:
    """Largest fall from a previous peak, as a negative fraction, from a
    series of daily returns."""
    wealth = np.cumprod(np.concatenate([[1.0], 1 + returns]))
    peaks = np.maximum.accumulate(wealth)
    return float((wealth / peaks - 1).min())


def _usable_series(series: dict[str, list[dict]]) -> tuple[dict[str, dict[date, float]], list[dict]]:
    """Drop stocks that are stale or too short, saying why."""
    by_ticker = {
        ticker: {_day(r["date"]): float(r["close"]) for r in rows if r.get("close")}
        for ticker, rows in series.items()
    }
    latest = {t: max(closes) for t, closes in by_ticker.items() if closes}
    newest = max(latest.values(), default=None)

    kept, excluded = {}, []
    for ticker, closes in by_ticker.items():
        if not closes:
            excluded.append({"ticker": ticker, "reason": "no prices stored"})
        elif newest - latest[ticker] > timedelta(days=STALE_AFTER_DAYS):
            excluded.append(
                {"ticker": ticker, "reason": f"prices end {latest[ticker]}, over "
                 f"{STALE_AFTER_DAYS} days before the others"}
            )
        elif len(closes) < MIN_RETURNS + 1:
            excluded.append({"ticker": ticker, "reason": f"only {len(closes)} days of prices"})
        else:
            kept[ticker] = closes
    return kept, excluded


def compute_market_stats(series: dict[str, list[dict]], computed_at: datetime) -> dict | None:
    """Statistics for every usable stock, or None if fewer than two stocks
    share enough history to say how they move together."""
    kept, excluded = _usable_series(series)
    if len(kept) < 2:
        return None

    tickers = sorted(kept)
    common = sorted(set.intersection(*(set(kept[t]) for t in tickers)))
    common = common[-(LOOKBACK_RETURNS + 1):]
    if len(common) < MIN_RETURNS + 1:
        return None

    closes = np.array([[kept[t][d] for t in tickers] for d in common])  # days x stocks
    returns = closes[1:] / closes[:-1] - 1

    breaks = np.abs(returns) > MAX_PLAUSIBLE_DAILY_MOVE
    data_breaks = [
        {"ticker": tickers[j], "date": datetime.combine(common[i + 1], datetime.min.time()),
         "daily_return": round(float(returns[i, j]), 6)}
        for i, j in zip(*np.nonzero(breaks), strict=True)
    ]
    returns = returns[~breaks.any(axis=1)]
    if len(returns) < MIN_RETURNS:
        return None

    sample_cov = np.cov(returns, rowvar=False)
    lw = LedoitWolf().fit(returns)
    cov = lw.covariance_ * TRADING_DAYS_PER_YEAR
    vols = np.sqrt(np.diag(cov))
    corr = cov / np.outer(vols, vols)

    equal = np.full(len(tickers), 1 / len(tickers))
    sample_vols = np.sqrt(np.diag(sample_cov) * TRADING_DAYS_PER_YEAR)

    def matrix(values: np.ndarray) -> dict[str, dict[str, float]]:
        return {
            a: {b: round(float(values[i, j]), 6) for j, b in enumerate(tickers)}
            for i, a in enumerate(tickers)
        }

    off_diagonal = corr[~np.eye(len(tickers), dtype=bool)]
    return {
        "as_of": datetime.combine(common[-1], datetime.min.time()),
        "start": datetime.combine(common[0], datetime.min.time()),
        "observations": len(returns),
        "tickers": tickers,
        "excluded": excluded,
        "data_breaks": data_breaks,
        "stocks": {
            t: {
                "annual_return": round(float(returns[:, i].mean() * TRADING_DAYS_PER_YEAR), 6),
                "annual_volatility": round(float(vols[i]), 6),
                "sample_annual_volatility": round(float(sample_vols[i]), 6),
                "max_drawdown": round(max_drawdown(returns[:, i]), 6),
            }
            for i, t in enumerate(tickers)
        },
        "covariance": matrix(cov),
        "correlation": matrix(corr),
        "shrinkage": round(float(lw.shrinkage_), 6),
        "average_correlation": round(float(off_diagonal.mean()), 6),
        # Diversification in one line: an equal-weight mix swings less than
        # the average stock in it, because the stocks don't move in lockstep.
        "average_stock_volatility": round(float(vols.mean()), 6),
        "equal_weight_volatility": round(float(np.sqrt(equal @ cov @ equal)), 6),
        "computed_at": computed_at,
        "version": MARKET_STATS_VERSION,
    }
