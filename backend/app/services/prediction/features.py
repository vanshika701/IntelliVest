"""Model inputs computed from daily prices, the Nifty 50 and India VIX.

Every feature at date t uses only data up to and including t's close, so
nothing looks ahead. Used unchanged for training and for live predictions.
"""

import numpy as np
import pandas as pd

from app.core.constants import TICKER_TO_SECTOR

# A one-day move this large is a data break (demerger, bad print), not a
# market move, so features and labels never span it. Same threshold as the
# Phase 7 market statistics job.
BREAK_THRESHOLD = 0.35

# Minimum days in a series before it gets a prediction (vol_63 needs 63).
MIN_HISTORY = 64

SECTOR_CODES: dict[str, int] = {
    sid: i for i, sid in enumerate(sorted(set(TICKER_TO_SECTOR.values())))
}

STOCK_FEATURES = [
    "ret_1",
    "ret_5",
    "ret_21",
    "ret_63",
    "ret_126",
    "ret_252",
    "vol_5",
    "vol_21",
    "vol_63",
    "vol_trend",
    "dist_ma50",
    "dist_ma200",
    "dist_high252",
    "dist_low252",
    "rsi_14",
    "volume_trend",
]
MARKET_FEATURES = [
    "mkt_ret_5",
    "mkt_ret_21",
    "mkt_ret_63",
    "mkt_vol_21",
    "mkt_dist_ma200",
    "vix",
    "vix_chg_5",
]
CROSS_FEATURES = ["rel_ret_63", "xs_rank_21", "xs_rank_63"]
# The model also takes the horizon, so one model covers every horizon.
FEATURE_COLUMNS = [*STOCK_FEATURES, *MARKET_FEATURES, *CROSS_FEATURES, "sector", "log_horizon"]
CATEGORICAL_FEATURES = ["sector"]


def _series_features(group: pd.DataFrame) -> pd.DataFrame:
    with np.errstate(divide="ignore", invalid="ignore"):
        out = _raw_series_features(group)
    # A flat stretch gives log(0); the model treats missing values natively.
    return out.replace([np.inf, -np.inf], np.nan)


def _raw_series_features(group: pd.DataFrame) -> pd.DataFrame:
    close = group["close"]
    log_close = np.log(close)
    daily = log_close.diff()
    out = pd.DataFrame(index=group.index)
    for days in (1, 5, 21, 63, 126, 252):
        out[f"ret_{days}"] = log_close - log_close.shift(days)
    for days in (5, 21, 63):
        out[f"vol_{days}"] = daily.rolling(days, min_periods=days).std()
    out["vol_trend"] = np.log(out["vol_21"] / out["vol_63"])
    out["dist_ma50"] = np.log(close / close.rolling(50, min_periods=50).mean())
    out["dist_ma200"] = np.log(close / close.rolling(200, min_periods=200).mean())
    out["dist_high252"] = np.log(close / close.rolling(252, min_periods=252).max())
    out["dist_low252"] = np.log(close / close.rolling(252, min_periods=252).min())
    gains = daily.clip(lower=0).rolling(14, min_periods=14).mean()
    losses = (-daily.clip(upper=0)).rolling(14, min_periods=14).mean()
    out["rsi_14"] = gains / (gains + losses)
    volume = group["volume"].replace(0, np.nan)
    out["volume_trend"] = np.log(
        volume.rolling(5, min_periods=3).mean() / volume.rolling(63, min_periods=40).mean()
    )
    out["days_of_history"] = np.arange(1, len(group) + 1)
    return out


def _with_dates(frame: pd.DataFrame) -> pd.DataFrame:
    """Same date type everywhere: Mongo, Yahoo and parquet differ in precision."""
    dates = pd.to_datetime(frame["date"])
    if dates.dt.tz is not None:
        dates = dates.dt.tz_localize(None)
    return frame.assign(date=dates.dt.normalize().astype("datetime64[ns]"))


def mark_segments(prices: pd.DataFrame) -> pd.DataFrame:
    """Sort and add `segment`: a new one starts at every data break."""
    prices = prices.sort_values(["ticker", "date"]).reset_index(drop=True)
    jump = np.log(prices["close"]).groupby(prices["ticker"]).diff().abs() > BREAK_THRESHOLD
    prices["segment"] = jump.groupby(prices["ticker"]).cumsum().astype(int)
    return prices


def market_features(market: pd.DataFrame) -> pd.DataFrame:
    """`market` has date, nifty and vix columns (one row per trading day)."""
    market = market.sort_values("date").reset_index(drop=True)
    log_nifty = np.log(market["nifty"])
    daily = log_nifty.diff()
    out = pd.DataFrame({"date": market["date"]})
    for days in (5, 21, 63):
        out[f"mkt_ret_{days}"] = log_nifty - log_nifty.shift(days)
    out["mkt_vol_21"] = daily.rolling(21, min_periods=21).std()
    out["mkt_dist_ma200"] = np.log(
        market["nifty"] / market["nifty"].rolling(200, min_periods=200).mean()
    )
    out["vix"] = market["vix"] / 100
    out["vix_chg_5"] = np.log(market["vix"] / market["vix"].shift(5))
    return out


def compute_features(prices: pd.DataFrame, market: pd.DataFrame) -> pd.DataFrame:
    """One row per (ticker, date) with every feature except `log_horizon`.

    `prices` has ticker, date, close and volume; `market` has date, nifty
    and vix. Dates are tz-naive midnights. Rows with under MIN_HISTORY days
    since the start or the last data break are dropped.
    """
    prices = mark_segments(_with_dates(prices[["ticker", "date", "close", "volume"]]))
    market = _with_dates(market)
    keys = [prices["ticker"], prices["segment"]]
    per_series = prices.groupby(keys, group_keys=False)[["close", "volume"]].apply(_series_features)
    frame = pd.concat([prices, per_series], axis=1)
    frame = frame[frame["days_of_history"] >= MIN_HISTORY].drop(columns="days_of_history")

    # Index data can lag a day on Yahoo, so take the latest market row on or
    # before each stock date, within a week.
    frame = pd.merge_asof(
        frame.sort_values("date"),
        market_features(market).sort_values("date"),
        on="date",
        direction="backward",
        tolerance=pd.Timedelta(days=7),
    )
    frame["rel_ret_63"] = frame["ret_63"] - frame["mkt_ret_63"]
    by_date = frame.groupby("date")
    frame["xs_rank_21"] = by_date["ret_21"].rank(pct=True)
    frame["xs_rank_63"] = by_date["ret_63"].rank(pct=True)
    frame["sector"] = frame["ticker"].map(SECTOR_CODES).fillna(-1).astype(int)
    frame = frame[frame["vol_63"] > 0]
    return frame.sort_values(["ticker", "date"]).reset_index(drop=True)


def with_horizon(features: pd.DataFrame, horizon_days: int) -> pd.DataFrame:
    return features.assign(log_horizon=np.log(horizon_days))


def scale(features: pd.DataFrame, horizon_days: int) -> pd.Series:
    """How big a typical move over the horizon is, from recent volatility.
    The model predicts returns in units of this scale."""
    return features["vol_63"] * np.sqrt(horizon_days)
