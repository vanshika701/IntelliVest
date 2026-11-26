"""Walk-forward backtest of the Phase 7 equity optimizer.

Question: does the minimum-variance stock mix the app recommends actually
deliver lower risk on data it has NOT seen, and at what cost in return,
compared with simple alternatives?

Method (no lookahead):
- Every REBALANCE_EVERY trading days, build the portfolio using only
  prices up to that day, with the app's own code
  (backend/app/services/market_stats.py and equity_optimizer.py, sentiment
  off). Hold it until the next rebalance, letting weights drift with
  prices, and record what actually happened.
- Charge TRADING_COST on every rupee bought or sold at a rebalance.
- Compare with an equal-weight mix of the same stocks (the fair baseline:
  same universe, same rebalancing, same costs) and the Nifty 50 index.
- Check the risk model itself: the volatility the optimizer predicted at
  each rebalance against the volatility that followed.

Known biases (stated, not fixed):
- Survivorship / hindsight: the 20 stocks are today's large caps, picked
  knowing they did well enough to stay large. That flatters every stock
  strategy against the index; comparisons BETWEEN the stock strategies
  share the bias.
- The Nifty 50 series (^NSEI) is a price index without dividends, while
  stock prices are dividend-adjusted, so the index is understated by
  roughly its dividend yield (about 1-1.5% a year).
- Sentiment can't be backtested: there are no stored historical FinBERT
  scores, so only the risk-based part of the optimizer is tested.

Run:
    cd ml && python3 backtest_portfolio.py           # uses cached prices if present
    cd ml && python3 backtest_portfolio.py --refresh # re-download from Yahoo
Writes ml/models/portfolio_backtest/metrics.json.
"""

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd

ML_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(ML_DIR.parent / "backend"))

from app.core.constants import STOCK_UNIVERSE
from app.services.equity_optimizer import optimize_equity
from app.services.market_stats import (
    LOOKBACK_RETURNS,
    MAX_PLAUSIBLE_DAILY_MOVE,
    MIN_RETURNS,
    TRADING_DAYS_PER_YEAR,
    compute_market_stats,
)

PRICES_CSV = ML_DIR / "data" / "raw" / "backtest_prices.csv"
OUTPUT_DIR = ML_DIR / "models" / "portfolio_backtest"
INDEX_TICKER = "^NSEI"
START = "2012-01-01"

REBALANCE_EVERY = 21  # about monthly
# Per rupee bought or sold. Securities transaction tax alone is 0.1% on
# each side of a delivery trade; exchange charges, stamp duty, GST and
# slippage on large caps add roughly another 0.05-0.1%. Our assumption.
TRADING_COST = 0.002
# For the Sharpe ratio: roughly what a liquid fund paid over the period
# (HDFC Liquid Fund: 6.9% a year over the last 3 years). Our assumption.
RISK_FREE_RATE = 0.06


def load_prices(refresh: bool) -> pd.DataFrame:
    if PRICES_CSV.exists() and not refresh:
        prices = pd.read_csv(PRICES_CSV, index_col=0, parse_dates=True)
    else:
        import yfinance as yf

        print(f"Downloading daily prices since {START} from Yahoo Finance...")
        prices = yf.download([*STOCK_UNIVERSE, INDEX_TICKER], start=START, auto_adjust=True, progress=False)["Close"]
        PRICES_CSV.parent.mkdir(parents=True, exist_ok=True)
        prices.to_csv(PRICES_CSV)
    # Every day all the stocks traded (drops a partial current day). The
    # index is missing some sessions, e.g. Diwali Muhurat trading: carry its
    # last value forward rather than drop those days, which would merge two
    # days of stock moves into one.
    stocks = prices[list(STOCK_UNIVERSE)].dropna()
    index = prices[INDEX_TICKER].reindex(stocks.index).ffill()
    return stocks.assign(**{INDEX_TICKER: index}).dropna()


def clean_returns(prices: pd.DataFrame) -> tuple[pd.DataFrame, list[dict]]:
    """Daily returns with corporate-action breaks set to 0, the same rule
    the app uses (market_stats.MAX_PLAUSIBLE_DAILY_MOVE)."""
    returns = prices.pct_change().iloc[1:]
    breaks = returns.abs() > MAX_PLAUSIBLE_DAILY_MOVE
    found = [
        {"ticker": t, "date": d.date().isoformat(), "daily_return": round(float(returns.at[d, t]), 4)}
        for t in returns.columns for d in returns.index[breaks[t]]
    ]
    return returns.mask(breaks, 0.0), found


def rows_for(prices: pd.DataFrame, end: int) -> dict[str, list[dict]]:
    """The price history the app would have had on day `end`, in the
    shape compute_market_stats expects."""
    window = prices.iloc[max(0, end - LOOKBACK_RETURNS): end + 1]
    return {
        t: [{"date": d.to_pydatetime(), "close": float(c)} for d, c in window[t].items()]
        for t in STOCK_UNIVERSE
    }


def run_strategy(returns: pd.DataFrame, targets: dict[int, pd.Series]) -> tuple[pd.Series, list[float]]:
    """Daily net returns of a strategy that resets to `targets[i]` on each
    rebalance day i and drifts in between; plus turnover per rebalance."""
    daily, turnovers = [], []
    weights = None
    for i in range(min(targets), len(returns)):
        if i in targets:
            target = targets[i]
            turnover = float((target - weights).abs().sum()) if weights is not None else 1.0
            turnovers.append(turnover)
            cost = turnover * TRADING_COST
            weights = target.copy()
        else:
            cost = 0.0
        day = returns.iloc[i]
        gross = float((weights * day[weights.index]).sum())
        daily.append(gross - cost)
        grown = weights * (1 + day[weights.index])
        weights = grown / grown.sum()
    return pd.Series(daily, index=returns.index[min(targets):]), turnovers


def metrics(daily: pd.Series) -> dict:
    wealth = (1 + daily).cumprod()
    years = len(daily) / TRADING_DAYS_PER_YEAR
    cagr = float(wealth.iloc[-1] ** (1 / years) - 1)
    vol = float(daily.std() * np.sqrt(TRADING_DAYS_PER_YEAR))
    drawdown = float((wealth / wealth.cummax() - 1).min())
    return {
        "cagr": round(cagr, 4),
        "annual_volatility": round(vol, 4),
        "max_drawdown": round(drawdown, 4),
        "sharpe": round((cagr - RISK_FREE_RATE) / vol, 3) if vol else None,
        "calmar": round(cagr / abs(drawdown), 3) if drawdown else None,
        "final_value_of_100": round(float(wealth.iloc[-1] * 100), 1),
    }


def yearly_returns(daily: pd.Series) -> dict[str, float]:
    return {str(y): round(float((1 + r).prod() - 1), 4) for y, r in daily.groupby(daily.index.year)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--refresh", action="store_true", help="re-download prices")
    args = parser.parse_args()

    prices = load_prices(args.refresh)
    returns, breaks = clean_returns(prices)
    stocks = returns[list(STOCK_UNIVERSE)]
    print(f"Prices: {prices.index[0].date()} to {prices.index[-1].date()}, {len(prices)} days")

    # First rebalance once a full year of returns is available.
    first = MIN_RETURNS + 1
    rebalance_days = list(range(first, len(returns), REBALANCE_EVERY))
    minvar_targets, equal_targets, calibration = {}, {}, []
    for n, i in enumerate(rebalance_days, 1):
        # Prices up to and including day i (returns index i is price index i+1).
        stats = compute_market_stats(rows_for(prices, i), datetime.now(UTC))
        result = optimize_equity(stats, use_sentiment=False)
        weights = pd.Series({s["ticker"]: s["weight"] for s in result["stocks"]})
        minvar_targets[i] = weights / weights.sum()
        equal_targets[i] = pd.Series(1 / len(stats["tickers"]), index=stats["tickers"])

        next_i = min(i + REBALANCE_EVERY, len(returns))
        realised = stocks.iloc[i:next_i]
        if len(realised) >= 10:
            calibration.append({
                "date": returns.index[i].date().isoformat(),
                "predicted": result["portfolio"]["annual_volatility"],
                "realised": float((realised[weights.index] @ minvar_targets[i]).std() * np.sqrt(TRADING_DAYS_PER_YEAR)),
                "equal_predicted": result["equal_weight"]["annual_volatility"],
                "equal_realised": float(realised[stats["tickers"]].mean(axis=1).std() * np.sqrt(TRADING_DAYS_PER_YEAR)),
                "holdings": result["portfolio"]["holdings"],
            })
        if n % 20 == 0:
            print(f"  rebalance {n}/{len(rebalance_days)} ({returns.index[i].date()})")

    minvar, minvar_turnover = run_strategy(stocks, minvar_targets)
    equal, equal_turnover = run_strategy(stocks, equal_targets)
    nifty = returns[INDEX_TICKER].iloc[first:]

    cal = pd.DataFrame(calibration)
    results = {
        "period": {"start": minvar.index[0].date().isoformat(), "end": minvar.index[-1].date().isoformat(),
                   "years": round(len(minvar) / TRADING_DAYS_PER_YEAR, 2), "rebalances": len(rebalance_days)},
        "assumptions": {
            "rebalance_every_trading_days": REBALANCE_EVERY,
            "trading_cost_per_rupee_traded": TRADING_COST,
            "risk_free_rate": RISK_FREE_RATE,
            "lookback_returns": LOOKBACK_RETURNS,
            "sentiment_used": False,
            "data_break_threshold": MAX_PLAUSIBLE_DAILY_MOVE,
        },
        "strategies": {
            "minimum_variance": {**metrics(minvar), "avg_turnover_per_rebalance": round(float(np.mean(minvar_turnover[1:])), 4),
                                 "avg_holdings": round(float(cal["holdings"].mean()), 1)},
            "equal_weight": {**metrics(equal), "avg_turnover_per_rebalance": round(float(np.mean(equal_turnover[1:])), 4)},
            "nifty_50_price_index": metrics(nifty),
        },
        "yearly_returns": {"minimum_variance": yearly_returns(minvar), "equal_weight": yearly_returns(equal),
                           "nifty_50_price_index": yearly_returns(nifty)},
        "risk_model_check": {
            "note": "Volatility each portfolio was predicted to have at rebalance vs what it had over the next month.",
            "minimum_variance": {"avg_predicted": round(float(cal["predicted"].mean()), 4),
                                 "avg_realised": round(float(cal["realised"].mean()), 4)},
            "equal_weight": {"avg_predicted": round(float(cal["equal_predicted"].mean()), 4),
                             "avg_realised": round(float(cal["equal_realised"].mean()), 4)},
            "months_min_variance_calmer_than_equal": round(float((cal["realised"] < cal["equal_realised"]).mean()), 3),
        },
        "data_breaks_zeroed": breaks,
        "known_biases": [
            "Survivorship/hindsight: today's 20 large caps were chosen knowing they stayed large; flatters stock strategies vs the index.",
            "Nifty 50 (^NSEI) excludes dividends; stock prices include them, so the index is understated by ~1-1.5% a year.",
            "Sentiment tilt not tested: no historical FinBERT scores exist.",
        ],
        "computed_at": datetime.now(UTC).isoformat(),
    }

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUTPUT_DIR / "metrics.json").write_text(json.dumps(results, indent=2))

    print(f"\nWalk-forward backtest, {results['period']['start']} to {results['period']['end']} "
          f"({results['period']['years']} years, {len(rebalance_days)} monthly rebalances)\n")
    header = f"{'Strategy':24} {'CAGR':>7} {'Vol':>7} {'MaxDD':>8} {'Sharpe':>7} {'₹100 →':>8}"
    print(header)
    for name, m in results["strategies"].items():
        print(f"{name:24} {m['cagr']:7.1%} {m['annual_volatility']:7.1%} {m['max_drawdown']:8.1%} "
              f"{m['sharpe']:7.2f} {m['final_value_of_100']:8.0f}")
    rc = results["risk_model_check"]
    print(f"\nRisk model: min-variance predicted {rc['minimum_variance']['avg_predicted']:.1%}, realised "
          f"{rc['minimum_variance']['avg_realised']:.1%}; calmer than equal weight in "
          f"{rc['months_min_variance_calmer_than_equal']:.0%} of months")
    print(f"Data breaks zeroed: {breaks}")
    print(f"Saved {OUTPUT_DIR / 'metrics.json'}")


if __name__ == "__main__":
    main()
