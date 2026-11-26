"""Offline training for the Phase 4 stock predictor.

    .venv/Scripts/python ml/train_stock_predictor.py            # full run
    .venv/Scripts/python ml/train_stock_predictor.py --refresh  # re-download prices
    .venv/Scripts/python ml/train_stock_predictor.py --quick    # small smoke run

What it predicts: the stock's return over a horizon of 1 to 504 trading
days (about 2 years), as a range (10th, 50th and 90th percentile) and a
chance of going up. One model covers every stock and every horizon: the
horizon is an input.

How: gradient-boosted trees (scikit-learn's HistGradientBoostingClassifier,
the same algorithm as LightGBM) sort the coming return, measured in units
of the stock's recent volatility, into ~15 buckets and give a probability
for each. backend/app/services/prediction/distribution.py turns those into
the range and the chance up.

Data: daily prices from Yahoo Finance for the 20 stocks in STOCK_UNIVERSE,
the Nifty 50 and India VIX, from March 2008 (when India VIX starts).
Saved to ml/data/raw/ (gitignored) so reruns use the same data.

Testing: walk-forward by calendar year. For each test year the model trains
only on rows whose whole label window ends before that year starts, so no
future price leaks in. It is compared against a baseline that uses the
stock's recent volatility alone, and against "always up" for direction.

Outputs (ml/models/stock_predictor/): model.joblib (gitignored, regenerate
with this script) and metrics.json (tracked).
"""

import argparse
import json
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import yfinance as yf
from scipy.stats import spearmanr
from sklearn.ensemble import HistGradientBoostingClassifier

ML_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(ML_DIR.parent / "backend"))

from app.core.constants import STOCK_UNIVERSE
from app.services.prediction.distribution import (
    HIGH_Q,
    LOW_Q,
    MID_Q,
    Buckets,
    chance_up,
    full_probabilities,
    quantiles,
)
from app.services.prediction.features import (
    BREAK_THRESHOLD,
    CATEGORICAL_FEATURES,
    FEATURE_COLUMNS,
    compute_features,
    scale,
    with_horizon,
)
from app.services.prediction.horizon import (
    HORIZON_GRID,
    HORIZON_GROUPS,
    horizon_group,
)

MODEL_VERSION = "1.0.0"
DATA_START = "2008-03-01"
RAW_DIR = ML_DIR / "data" / "raw"
MODEL_DIR = ML_DIR / "models" / "stock_predictor"
NIFTY, VIX = "^NSEI", "^INDIAVIX"

TEST_YEARS = (2020, 2021, 2022, 2023, 2024, 2025)
# Training keeps every STRIDE-th trading day per horizon. Neighbouring days
# share almost all of their label window, so this loses little information
# and cuts training time several times over.
STRIDE = 4
MODEL_PARAMS = {
    "max_iter": 250,
    "learning_rate": 0.05,
    "max_leaf_nodes": 31,
    "min_samples_leaf": 400,
    "l2_regularization": 1.0,
    "early_stopping": False,
    "random_state": 42,
}
LEVELS = (LOW_Q, MID_Q, HIGH_Q)


# --- data ---------------------------------------------------------------


def _history(ticker: str) -> pd.DataFrame:
    raw = yf.Ticker(ticker).history(start=DATA_START, interval="1d", timeout=30)
    if raw.empty:
        raise RuntimeError(f"No data for {ticker}")
    raw = raw.dropna(subset=["Close"])
    dates = pd.to_datetime([d.date() for d in raw.index])
    return pd.DataFrame(
        {"date": dates, "close": raw["Close"].to_numpy(), "volume": raw["Volume"].to_numpy()}
    )


def load_data(refresh: bool) -> tuple[pd.DataFrame, pd.DataFrame]:
    prices_path, market_path = RAW_DIR / "stock_history.parquet", RAW_DIR / "market_history.parquet"
    if not refresh and prices_path.exists() and market_path.exists():
        return pd.read_parquet(prices_path), pd.read_parquet(market_path)
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    frames = []
    for ticker in STOCK_UNIVERSE:
        frame = _history(ticker)
        frame.insert(0, "ticker", ticker)
        frames.append(frame)
        print(f"  {ticker}: {len(frame)} days from {frame['date'].min().date()}")
    prices = pd.concat(frames, ignore_index=True)
    prices = prices[prices["close"] > 0]
    nifty, vix = _history(NIFTY), _history(VIX)
    market = (
        nifty[["date", "close"]]
        .rename(columns={"close": "nifty"})
        .merge(vix[["date", "close"]].rename(columns={"close": "vix"}), on="date", how="inner")
    )
    prices.to_parquet(prices_path, index=False)
    market.to_parquet(market_path, index=False)
    return prices, market


# --- labelled rows ----------------------------------------------------------


def labelled_rows(features: pd.DataFrame) -> pd.DataFrame:
    """One row per (ticker, date, horizon) with the realised return.

    Labels never cross a data break: the future close must be in the same
    segment. `train_row` marks every STRIDE-th trading day, offset per
    horizon so different horizons see different days.
    """
    day_index = features["date"].rank(method="dense").astype(int)
    group = features.groupby(["ticker", "segment"])
    log_close = np.log(features["close"])
    parts = []
    for h in HORIZON_GRID:
        rows = with_horizon(features, h).assign(
            horizon=h,
            label_end=group["date"].shift(-h),
            log_return=np.log(group["close"].shift(-h)) - log_close,
            train_row=(day_index + h) % STRIDE == 0,
        )
        rows = rows[rows["log_return"].notna()]
        parts.append(rows.assign(target=rows["log_return"] / scale(rows, h)))
    return pd.concat(parts, ignore_index=True)


# --- model ----------------------------------------------------------------


def fit(train: pd.DataFrame, params: dict) -> tuple[HistGradientBoostingClassifier, Buckets]:
    buckets = Buckets.fit(train["target"].to_numpy())
    model = HistGradientBoostingClassifier(
        **params, categorical_features=[FEATURE_COLUMNS.index(c) for c in CATEGORICAL_FEATURES]
    )
    model.fit(train[FEATURE_COLUMNS].to_numpy(), buckets.label(train["target"].to_numpy()))
    return model, buckets


def predict(model, buckets: Buckets, rows: pd.DataFrame) -> pd.DataFrame:
    probs = full_probabilities(
        model.predict_proba(rows[FEATURE_COLUMNS].to_numpy()), model.classes_, buckets.count
    )
    q = quantiles(probs, buckets, LEVELS)
    s = scale(rows, rows["horizon"]).to_numpy()[:, None]
    out = pd.DataFrame(q * s, columns=["low", "mid", "high"], index=rows.index)
    out["chance_up"] = chance_up(probs, buckets)
    return out


def baseline(train: pd.DataFrame, rows: pd.DataFrame) -> pd.DataFrame:
    """Volatility alone: the training targets' percentiles for each horizon,
    scaled by the stock's recent volatility. No other inputs."""
    by_h = train.groupby("horizon")["target"]
    q = by_h.quantile(list(LEVELS)).unstack()
    up = train.assign(up=train["log_return"] > 0).groupby("horizon")["up"].mean()
    s = scale(rows, rows["horizon"])
    out = pd.DataFrame(index=rows.index)
    for name, level in zip(("low", "mid", "high"), LEVELS, strict=True):
        out[name] = rows["horizon"].map(q[level]) * s
    out["chance_up"] = rows["horizon"].map(up)
    return out


# --- evaluation ---------------------------------------------------------------


def pinball(actual: np.ndarray, pred: pd.DataFrame) -> float:
    total = 0.0
    for name, level in zip(("low", "mid", "high"), LEVELS, strict=True):
        diff = actual - pred[name].to_numpy()
        total += np.mean(np.maximum(level * diff, (level - 1) * diff))
    return total / len(LEVELS)


def rank_scores(rows: pd.DataFrame, pred: pd.DataFrame) -> tuple[float, float]:
    """Mean Spearman correlation between predicted and real returns across
    stocks on the same day, and the mean return gap between the top 5 and
    bottom 5 predicted stocks (in %)."""
    frame = rows[["date", "horizon", "log_return"]].assign(mid=pred["mid"])
    ics, gaps = [], []
    for _, day in frame.groupby(["date", "horizon"]):
        if len(day) < 10:
            continue
        ic = spearmanr(day["mid"], day["log_return"]).statistic
        if not np.isnan(ic):
            ics.append(ic)
        ordered = day.sort_values("mid")
        gaps.append(
            np.expm1(ordered["log_return"].tail(5)).mean()
            - np.expm1(ordered["log_return"].head(5)).mean()
        )
    return float(np.mean(ics)) if ics else float("nan"), float(
        np.mean(gaps) * 100
    ) if gaps else float("nan")


def score(rows: pd.DataFrame, pred: pd.DataFrame, base: pd.DataFrame) -> dict:
    actual = rows["log_return"].to_numpy()
    up = actual > 0
    ic, gap = rank_scores(rows, pred)
    base_ic, base_gap = rank_scores(rows, base)
    return {
        "rows": len(rows),
        "range_hit_rate": float(np.mean((actual >= pred["low"]) & (actual <= pred["high"]))),
        "baseline_range_hit_rate": float(
            np.mean((actual >= base["low"]) & (actual <= base["high"]))
        ),
        "range_width_pct": float(np.mean(np.expm1(pred["high"]) - np.expm1(pred["low"])) * 100),
        "baseline_range_width_pct": float(
            np.mean(np.expm1(base["high"]) - np.expm1(base["low"])) * 100
        ),
        "pinball_loss": pinball(actual, pred),
        "baseline_pinball_loss": pinball(actual, base),
        "direction_accuracy": float(np.mean((pred["chance_up"] > 0.5) == up)),
        "always_up_accuracy": float(np.mean(up)),
        "brier": float(np.mean((pred["chance_up"] - up) ** 2)),
        "baseline_brier": float(np.mean((base["chance_up"] - up) ** 2)),
        "rank_correlation": ic,
        "baseline_rank_correlation": base_ic,
        "top5_minus_bottom5_pct": gap,
        "baseline_top5_minus_bottom5_pct": base_gap,
    }


def score_by_group(rows: pd.DataFrame, pred: pd.DataFrame, base: pd.DataFrame) -> dict:
    groups = rows["horizon"].map(horizon_group)
    out = {}
    for label, _ in HORIZON_GROUPS:
        mask = (groups == label).to_numpy()
        if mask.any():
            out[label] = score(rows[mask], pred[mask], base[mask])
    return out


def walk_forward(
    data: pd.DataFrame, test_years: tuple[int, ...], params: dict
) -> tuple[dict, dict]:
    folds = {}
    preds, bases, tests = [], [], []
    for year in test_years:
        start, end = pd.Timestamp(year, 1, 1), pd.Timestamp(year + 1, 1, 1)
        train = data[(data["label_end"] < start) & data["train_row"]]
        test = data[(data["date"] >= start) & (data["date"] < end)]
        if test.empty or train.empty:
            continue
        began = time.time()
        model, buckets = fit(train, params)
        pred, base = predict(model, buckets, test), baseline(train, test)
        folds[str(year)] = {
            "train_rows": len(train),
            "train_seconds": round(time.time() - began, 1),
            "groups": score_by_group(test, pred, base),
        }
        print(
            f"  {year}: trained on {len(train):,} rows in {folds[str(year)]['train_seconds']}s, tested {len(test):,}"
        )
        preds.append(pred)
        bases.append(base)
        tests.append(test)
    all_tests = pd.concat(tests)
    return folds, score_by_group(all_tests, pd.concat(preds), pd.concat(bases))


# --- main -------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--refresh", action="store_true", help="re-download prices")
    parser.add_argument("--quick", action="store_true", help="2 test years, fewer trees")
    args = parser.parse_args()

    started = time.time()
    print("Loading prices...")
    prices, market = load_data(args.refresh)
    print("Computing features...")
    features = compute_features(prices, market)
    breaks = features.groupby("ticker")["segment"].max()
    data = labelled_rows(features)
    print(
        f"  {len(features):,} stock-days, {len(data):,} labelled rows, {int(data['train_row'].sum()):,} kept for training"
    )

    params = {**MODEL_PARAMS, "max_iter": 60} if args.quick else MODEL_PARAMS
    years = TEST_YEARS[-2:] if args.quick else TEST_YEARS
    print("Walk-forward test...")
    folds, overall = walk_forward(data, years, params)

    print("Training the final model on all data...")
    final_train = data[data["train_row"]]
    model, buckets = fit(final_train, params)

    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    artifact = {
        "model": model,
        "bucket_edges": buckets.edges,
        "bucket_low": buckets.low,
        "bucket_high": buckets.high,
        "feature_columns": FEATURE_COLUMNS,
        "horizons": list(HORIZON_GRID),
        "version": MODEL_VERSION,
    }
    joblib.dump(artifact, MODEL_DIR / "model.joblib", compress=3)

    metrics = {
        "model_version": MODEL_VERSION,
        "trained_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "quick_run": args.quick,
        "model": "HistGradientBoostingClassifier over volatility-scaled return buckets",
        "params": params,
        "buckets": len(buckets.edges) + 1,
        "data": {
            "source": "Yahoo Finance via yfinance (adjusted daily closes)",
            "stocks": STOCK_UNIVERSE,
            "market": [NIFTY, VIX],
            "start": str(features["date"].min().date()),
            "end": str(features["date"].max().date()),
            "stock_days": len(features),
            "labelled_rows": len(data),
            "training_rows_final": len(final_train),
            "stride": STRIDE,
            "data_breaks": {t: int(n) for t, n in breaks.items() if n},
            "break_threshold": BREAK_THRESHOLD,
        },
        "features": FEATURE_COLUMNS,
        "horizons_trading_days": list(HORIZON_GRID),
        "evaluation": {
            "method": "Walk-forward by calendar year; training rows' label windows end before the test year",
            "test_years": [int(y) for y in folds],
            "baseline": "Recent volatility alone (training percentiles per horizon, scaled by vol_63 x sqrt(h))",
            "range": "10th to 90th percentile; a calibrated range holds the real return 80% of the time",
            "overall": overall,
            "folds": folds,
        },
        "seconds": round(time.time() - started),
    }
    (MODEL_DIR / "metrics.json").write_text(json.dumps(metrics, indent=2))

    print("\nResults (all test years pooled):")
    for label, m in overall.items():
        print(
            f"  {label:22} range hit {m['range_hit_rate']:.1%} (base {m['baseline_range_hit_rate']:.1%})"
            f"  pinball {m['pinball_loss']:.5f} (base {m['baseline_pinball_loss']:.5f})"
            f"  direction {m['direction_accuracy']:.1%} (always-up {m['always_up_accuracy']:.1%})"
            f"  rank corr {m['rank_correlation']:.3f}  top5-bottom5 {m['top5_minus_bottom5_pct']:.2f}%"
        )
    print(f"\nSaved to {MODEL_DIR} in {metrics['seconds']}s")


if __name__ == "__main__":
    main()
