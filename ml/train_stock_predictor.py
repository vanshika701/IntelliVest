"""Offline training for the Phase 4 stock predictor.

    .venv/Scripts/python ml/train_stock_predictor.py            # full run
    .venv/Scripts/python ml/train_stock_predictor.py --refresh  # re-download prices
    .venv/Scripts/python ml/train_stock_predictor.py --quick    # small smoke run
    .venv/Scripts/python ml/train_stock_predictor.py --universe broad --model-dir ml/models/stock_predictor_broad
        # ~173 NSE stocks of every size; run ml/download_broad_universe.py first

What it predicts: how the stock does against the Nifty 50 over a horizon
of 1 to 504 trading days (about 2 years): its log return minus the
Nifty's over the same days. Output is a range (10th, 50th and 90th
percentile) and a chance of beating the Nifty. One model covers every
stock and every horizon: the horizon is an input.

Why against the Nifty (model 2.0.0): model 1.0.0 predicted the plain
return, and since these stocks mostly rose, it nearly always said "up"
and never beat guessing "up". Beating the market is what a stock pick is
for, and about half of stocks lag it in any period.

How: gradient-boosted trees (scikit-learn's HistGradientBoostingClassifier,
the same algorithm as LightGBM) sort the coming excess return, measured in units
of the stock's recent volatility, into ~15 buckets and give a probability
for each. backend/app/services/prediction/distribution.py turns those into
the range and the chance of beating the Nifty.

Data: daily prices from Yahoo Finance for the 20 stocks in STOCK_UNIVERSE,
the Nifty 50 and India VIX, from March 2008 (when India VIX starts).
Saved to ml/data/raw/ (gitignored) so reruns use the same data.

Testing: walk-forward by calendar year. For each test year the model trains
only on rows whose whole label window ends before that year starts, so no
future price leaks in. It is compared against a baseline that uses the
stock's recent volatility alone, and against always making the more
common call (beat or lag) for direction.

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
    chance_above_zero,
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

MODEL_VERSIONS = {"tracked": "2.0.0", "broad": "3.0.0"}
TARGET = "excess_log_return_vs_nifty"
DATA_START = "2008-03-01"
RAW_DIR = ML_DIR / "data" / "raw"
BROAD_HISTORY = RAW_DIR / "broad_history.parquet"
MODEL_DIR = ML_DIR / "models" / "stock_predictor"
NIFTY, VIX = "^NSEI", "^INDIAVIX"

TEST_YEARS = (2020, 2021, 2022, 2023, 2024, 2025)
# Training keeps every STRIDE-th trading day per horizon. Neighbouring days
# share almost all of their label window, so this loses little information
# and cuts training time several times over.
STRIDE = 4
# The broad universe has ~9x the stock-days. Keeping every 8th trading day
# for training and testing alike (the same days for every stock, so
# same-day comparisons between stocks still work) keeps it within a
# laptop's memory and a couple of hours.
BROAD_STRIDE = 8
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
        {
            "date": dates,
            "close": raw["Close"].to_numpy(),
            "volume": raw["Volume"].to_numpy(),
        }
    )


def load_data(
    refresh: bool, universe: str = "tracked"
) -> tuple[pd.DataFrame, pd.DataFrame]:
    prices_path, market_path = (
        RAW_DIR / "stock_history.parquet",
        RAW_DIR / "market_history.parquet",
    )
    if universe == "broad":
        if not BROAD_HISTORY.exists():
            sys.exit("Run ml/download_broad_universe.py first")
        if not market_path.exists():
            load_data(refresh=True)
        return pd.read_parquet(BROAD_HISTORY), pd.read_parquet(market_path)
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
        .merge(
            vix[["date", "close"]].rename(columns={"close": "vix"}),
            on="date",
            how="inner",
        )
    )
    prices.to_parquet(prices_path, index=False)
    market.to_parquet(market_path, index=False)
    return prices, market


# --- labelled rows ----------------------------------------------------------


def labelled_rows(
    features: pd.DataFrame, stride: int = STRIDE, thin: bool = False
) -> pd.DataFrame:
    """One row per (ticker, date, horizon) with the realised excess return:
    the stock's log return minus the Nifty's over the same trading days.

    Labels never cross a data break: the future close must be in the same
    segment. `train_row` marks every stride-th trading day, offset per
    horizon so different horizons see different days. With `thin`, only
    those rows are kept, for testing too.
    """
    day_index = features["date"].rank(method="dense").astype(int)
    group = features.groupby(["ticker", "segment"])
    log_close = np.log(features["close"])
    log_nifty = np.log(features["nifty_close"])
    parts = []
    for h in HORIZON_GRID:
        rows = with_horizon(features, h).assign(
            horizon=h,
            label_end=group["date"].shift(-h),
            stock_return=np.log(group["close"].shift(-h)) - log_close,
            log_return=(np.log(group["close"].shift(-h)) - log_close)
            - (np.log(group["nifty_close"].shift(-h)) - log_nifty),
            train_row=(day_index + h) % stride == 0,
        )
        rows = rows[rows["log_return"].notna() & (rows["train_row"] | (not thin))]
        parts.append(rows.assign(target=rows["log_return"] / scale(rows, h)))
    return pd.concat(parts, ignore_index=True)


# --- model ----------------------------------------------------------------


def fit(
    train: pd.DataFrame, params: dict
) -> tuple[HistGradientBoostingClassifier, Buckets]:
    buckets = Buckets.fit(train["target"].to_numpy())
    model = HistGradientBoostingClassifier(
        **params,
        categorical_features=[FEATURE_COLUMNS.index(c) for c in CATEGORICAL_FEATURES],
    )
    model.fit(
        train[FEATURE_COLUMNS].to_numpy(), buckets.label(train["target"].to_numpy())
    )
    return model, buckets


def predict(model, buckets: Buckets, rows: pd.DataFrame) -> pd.DataFrame:
    probs = full_probabilities(
        model.predict_proba(rows[FEATURE_COLUMNS].to_numpy()),
        model.classes_,
        buckets.count,
    )
    q = quantiles(probs, buckets, LEVELS)
    s = scale(rows, rows["horizon"]).to_numpy()[:, None]
    out = pd.DataFrame(q * s, columns=["low", "mid", "high"], index=rows.index)
    out["chance_beat"] = chance_above_zero(probs, buckets)
    return out


def baseline(train: pd.DataFrame, rows: pd.DataFrame) -> pd.DataFrame:
    """Volatility alone: the training targets' percentiles for each horizon,
    scaled by the stock's recent volatility. No other inputs."""
    by_h = train.groupby("horizon")["target"]
    q = by_h.quantile(list(LEVELS)).unstack()
    beat = train.assign(beat=train["log_return"] > 0).groupby("horizon")["beat"].mean()
    s = scale(rows, rows["horizon"])
    out = pd.DataFrame(index=rows.index)
    for name, level in zip(("low", "mid", "high"), LEVELS, strict=True):
        out[name] = rows["horizon"].map(q[level]) * s
    out["chance_beat"] = rows["horizon"].map(beat)
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
    beat = actual > 0
    ic, gap = rank_scores(rows, pred)
    base_ic, base_gap = rank_scores(rows, base)
    return {
        "rows": len(rows),
        "range_hit_rate": float(
            np.mean((actual >= pred["low"]) & (actual <= pred["high"]))
        ),
        "baseline_range_hit_rate": float(
            np.mean((actual >= base["low"]) & (actual <= base["high"]))
        ),
        "range_width_pct": float(
            np.mean(np.expm1(pred["high"]) - np.expm1(pred["low"])) * 100
        ),
        "baseline_range_width_pct": float(
            np.mean(np.expm1(base["high"]) - np.expm1(base["low"])) * 100
        ),
        "pinball_loss": pinball(actual, pred),
        "baseline_pinball_loss": pinball(actual, base),
        "beat_share": float(np.mean(beat)),
        "call_accuracy": float(np.mean((pred["chance_beat"] > 0.5) == beat)),
        # Always calling the more common outcome (beat or lag).
        "majority_call_accuracy": float(max(np.mean(beat), 1 - np.mean(beat))),
        "brier": float(np.mean((pred["chance_beat"] - beat) ** 2)),
        "baseline_brier": float(np.mean((base["chance_beat"] - beat) ** 2)),
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
) -> tuple[dict, dict, dict]:
    """Per-year results, pooled results, and pooled results for the 20
    tracked stocks alone."""
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
    all_tests, all_preds, all_bases = (
        pd.concat(tests),
        pd.concat(preds),
        pd.concat(bases),
    )
    tracked = all_tests["ticker"].isin(STOCK_UNIVERSE).to_numpy()
    return (
        folds,
        score_by_group(all_tests, all_preds, all_bases),
        score_by_group(all_tests[tracked], all_preds[tracked], all_bases[tracked]),
    )


def latest_day_check(
    model, buckets: Buckets, features: pd.DataFrame, horizon: int = 21
) -> dict:
    """On the newest day: how many stocks are called to lag the Nifty, and
    whether recent losers get higher chances (the 1.0.0 problem)."""
    day = features["date"].max()
    rows = with_horizon(features[features["date"] == day], horizon).assign(
        horizon=horizon
    )
    pred = predict(model, buckets, rows)
    return {
        "date": str(day.date()),
        "horizon_days": horizon,
        "stocks": len(rows),
        "share_called_to_lag": float(np.mean(pred["chance_beat"] < 0.5)),
        "chance_beat_min": float(pred["chance_beat"].min()),
        "chance_beat_max": float(pred["chance_beat"].max()),
        "corr_past_3m_return_vs_chance_beat": float(
            np.corrcoef(rows["ret_63"], pred["chance_beat"])[0, 1]
        ),
    }


# --- main -------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--refresh", action="store_true", help="re-download prices")
    parser.add_argument(
        "--quick", action="store_true", help="2 test years, fewer trees"
    )
    parser.add_argument("--universe", choices=["tracked", "broad"], default="tracked")
    parser.add_argument("--model-dir", type=Path, default=MODEL_DIR)
    args = parser.parse_args()
    model_dir = (
        args.model_dir
        if args.model_dir.is_absolute()
        else ML_DIR.parent / args.model_dir
    )
    version = MODEL_VERSIONS[args.universe]
    stride = BROAD_STRIDE if args.universe == "broad" else STRIDE

    started = time.time()
    print("Loading prices...")
    prices, market = load_data(args.refresh, args.universe)
    print("Computing features...")
    features = compute_features(prices, market)
    breaks = features.groupby("ticker")["segment"].max()
    data = labelled_rows(features, stride, thin=args.universe == "broad")
    print(
        f"  {len(features):,} stock-days, {len(data):,} labelled rows, {int(data['train_row'].sum()):,} kept for training"
    )

    params = {**MODEL_PARAMS, "max_iter": 60} if args.quick else MODEL_PARAMS
    years = TEST_YEARS[-2:] if args.quick else TEST_YEARS
    print("Walk-forward test...")
    folds, overall, tracked_overall = walk_forward(data, years, params)

    print("Training the final model on all data...")
    final_train = data[data["train_row"]]
    model, buckets = fit(final_train, params)

    check = latest_day_check(model, buckets, features)
    model_dir.mkdir(parents=True, exist_ok=True)
    artifact = {
        "model": model,
        "bucket_edges": buckets.edges,
        "bucket_low": buckets.low,
        "bucket_high": buckets.high,
        "target": TARGET,
        "feature_columns": FEATURE_COLUMNS,
        "horizons": list(HORIZON_GRID),
        "version": version,
    }
    joblib.dump(artifact, model_dir / "model.joblib", compress=3)

    metrics = {
        "model_version": version,
        "universe": args.universe,
        "target": TARGET,
        "trained_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "quick_run": args.quick,
        "model": "HistGradientBoostingClassifier over volatility-scaled return buckets",
        "params": params,
        "buckets": len(buckets.edges) + 1,
        "data": {
            "source": "Yahoo Finance via yfinance (adjusted daily closes)",
            "stocks": sorted(features["ticker"].unique().tolist()),
            "market": [NIFTY, VIX],
            "start": str(features["date"].min().date()),
            "end": str(features["date"].max().date()),
            "stock_days": len(features),
            "labelled_rows": len(data),
            "training_rows_final": len(final_train),
            "stride": stride,
            "test_rows_thinned": args.universe == "broad",
            "data_breaks": {t: int(n) for t, n in breaks.items() if n},
            "break_threshold": BREAK_THRESHOLD,
        },
        "features": FEATURE_COLUMNS,
        "horizons_trading_days": list(HORIZON_GRID),
        "evaluation": {
            "method": "Walk-forward by calendar year; training rows' label windows end before the test year",
            "test_years": [int(y) for y in folds],
            "baseline": "Recent volatility alone (training percentiles per horizon, scaled by vol_63 x sqrt(h))",
            "range": "10th to 90th percentile; a calibrated range holds the real excess return 80% of the time",
            "overall": overall,
            "tracked_stocks_only": tracked_overall,
            "folds": folds,
        },
        "latest_day_check": check,
        "seconds": round(time.time() - started),
    }
    (model_dir / "metrics.json").write_text(json.dumps(metrics, indent=2))

    for title, results in (
        ("all stocks", overall),
        ("20 tracked stocks only", tracked_overall),
    ):
        print(f"\nResults, {title} (all test years pooled):")
        print_results(results)
    print(f"\nLatest day check: {check}")
    print(f"\nSaved to {model_dir} in {metrics['seconds']}s")


def print_results(results: dict) -> None:
    for label, m in results.items():
        print(
            f"  {label:22} range hit {m['range_hit_rate']:.1%} (base {m['baseline_range_hit_rate']:.1%})"
            f"  pinball {m['pinball_loss']:.5f} (base {m['baseline_pinball_loss']:.5f})"
            f"  beat call {m['call_accuracy']:.1%} (majority {m['majority_call_accuracy']:.1%}, beat share {m['beat_share']:.1%})"
            f"  rank corr {m['rank_correlation']:.3f}  top5-bottom5 {m['top5_minus_bottom5_pct']:.2f}%"
        )


if __name__ == "__main__":
    main()
