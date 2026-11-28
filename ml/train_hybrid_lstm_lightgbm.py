"""Research run: LSTM + LightGBM hybrid for the Phase 4 stock predictor.

    .venv/Scripts/python ml/train_hybrid_lstm_lightgbm.py           # full run
    .venv/Scripts/python ml/train_hybrid_lstm_lightgbm.py --quick   # smoke run

Same task, data, labels and walk-forward test as model 3.0.0
(train_stock_predictor.py --universe broad): 173 NSE stocks, excess log
return over the Nifty 50 for 17 horizons (1 to 504 trading days), test
years 2020-2025, every 8th trading day.

Papers this follows:
- Tian et al., "Stock price prediction based on LSTM and LightGBM hybrid
  model", J. Supercomputing 78 (2022), doi:10.1007/s11227-022-04326-5.
- Huang, "Stock Price Prediction Based on LSTM-LightGBM Fusion Model",
  AEMSS 2025 (Atlantis Press): stacking the two models.
- Yu et al., "Gradient Boosting Decision Tree with LSTM for Investment
  Prediction", arXiv:2505.23084 (2025): an ensemble of LSTM and GBDTs.

The papers combine the two models in two ways, and both are tested here:
1. Stacking: the LSTM reads the last 64 days of daily moves (a sequence)
   and its predictions become extra LightGBM inputs next to the 27
   hand-made features.
2. Ensemble: average the LSTM's and LightGBM's predicted ranges and
   chances.

Leakage: when LSTM outputs are used as LightGBM training inputs they must
be out-of-sample, or LightGBM learns to over-trust them. So the LSTM is
trained walk-forward too: for each year from OOF_START, a fresh LSTM
trained only on labels ending before that year predicts that year. The
stacked LightGBM for test year Y then trains on rows from OOF_START up to
Y, all of which carry out-of-sample LSTM values. That gives it less
history than 3.0.0 (which starts in 2008), so LightGBM alone is also run
on the same shorter window to separate the two effects.

Models compared (all on identical test rows):
- lgbm_full:  LightGBM, 3.0.0's inputs and training window
- lgbm_same:  LightGBM, 3.0.0's inputs, the stacked model's window
- lstm:       LSTM alone
- ensemble:   average of lgbm_full and lstm
- stacked:    LightGBM with the LSTM's four outputs as extra inputs
plus the volatility-only baseline, and 3.0.0's recorded numbers.

Output: ml/models/stock_predictor_hybrid/metrics.json (and per-year
checkpoints, gitignored). Nothing here changes the shipped model.
"""

import argparse
import gc
import json
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

import joblib
import lightgbm as lgb
import numpy as np
import pandas as pd
import torch
from torch import nn

ML_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(ML_DIR))

import train_stock_predictor as tsp
from app.services.prediction.distribution import (
    Buckets,
    chance_above_zero,
    full_probabilities,
    quantiles,
)
from app.services.prediction.features import (
    FEATURE_COLUMNS,
    compute_features,
)
from app.services.prediction.horizon import HORIZON_GRID, HORIZON_GROUPS, horizon_group
from app.services.prediction.sequence import (
    SEQ_LEN,
    build_net,
    sequence_inputs,
    windows,
)
from app.services.prediction.sequence import predict as predict_lstm

OUT_DIR = ML_DIR / "models" / "stock_predictor_hybrid"
LSTM_STRIDE = 4  # LSTM training samples: every 4th trading day per stock
OOF_START = 2014
LSTM_COLUMNS = ["lstm_q10", "lstm_q50", "lstm_q90", "lstm_beat"]
STACKED_COLUMNS = [*FEATURE_COLUMNS, *LSTM_COLUMNS]
H = len(HORIZON_GRID)
THREADS = 6

LGBM_PARAMS = {
    # Matched to 3.0.0's HistGradientBoosting settings.
    "objective": "multiclass",
    "n_estimators": 250,
    "learning_rate": 0.05,
    "num_leaves": 31,
    "min_child_samples": 400,
    "reg_lambda": 1.0,
    "max_bin": 255,
    "n_jobs": THREADS,
    "random_state": 42,
    "verbose": -1,
}
LSTM_PARAMS = {
    "hidden": 48,
    "dropout": 0.2,
    "lr": 2e-3,
    "batch": 1024,
    "max_epochs": 8,
    "patience": 2,
    "val_share": 0.15,
    "max_samples": 220_000,
    "beat_loss_weight": 0.5,
}


# --- sequences and per-day targets -------------------------------------------


def day_targets(f: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
    """For every stock-day and horizon: the volatility-scaled excess
    return (same as the tree model's target) and the day its label window
    ends (as days since 1970; huge when there is no label)."""
    g = f.groupby(["ticker", "segment"], sort=False)
    log_close, log_nifty = np.log(f["close"]), np.log(f["nifty_close"])
    day = f["date"].to_numpy().astype("datetime64[D]").astype(np.int64)
    targets = np.full((len(f), H), np.nan, dtype=np.float32)
    ends = np.full((len(f), H), np.iinfo(np.int64).max, dtype=np.int64)
    day_series = pd.Series(day, index=f.index)
    for k, h in enumerate(HORIZON_GRID):
        excess = (np.log(g["close"].shift(-h)) - log_close) - (
            np.log(g["nifty_close"].shift(-h)) - log_nifty
        )
        targets[:, k] = (excess / (f["vol_63"] * np.sqrt(h))).to_numpy(np.float32)
        end = day_series.groupby([f["ticker"], f["segment"]]).shift(-h)
        has = end.notna().to_numpy()
        ends[has, k] = end.to_numpy()[has].astype(np.int64)
    return targets, ends


def year_day(year: int) -> int:
    return int(np.datetime64(f"{year}-01-01", "D").astype(np.int64))


# --- LSTM --------------------------------------------------------------------


QUANTS = torch.tensor([0.1, 0.5, 0.9])


def batch_x(x: np.ndarray, idx: np.ndarray) -> torch.Tensor:
    return torch.from_numpy(windows(x, idx))


def lstm_loss(out: torch.Tensor, y: torch.Tensor, mask: torch.Tensor, beat_w: float):
    yq = y.unsqueeze(-1)
    diff = yq - out[..., :3]
    pin = torch.maximum(QUANTS * diff, (QUANTS - 1) * diff).mean(-1)
    bce = nn.functional.binary_cross_entropy_with_logits(
        out[..., 3], (y > 0).float(), reduction="none"
    )
    per = (pin + beat_w * bce) * mask
    return per.sum() / mask.sum().clamp(min=1)


def train_lstm(
    x: np.ndarray,
    targets: np.ndarray,
    ends: np.ndarray,
    samples: np.ndarray,
    cutoff: int,
    params: dict,
    seed: int,
) -> tuple:
    """Fit on stock-days `samples`, using only labels that end before
    `cutoff`. The last val_share of dates is held out to pick the epoch."""
    rng = np.random.default_rng(seed)
    torch.manual_seed(seed)
    mask_all = (ends[samples] < cutoff) & np.isfinite(targets[samples])
    samples = samples[mask_all.any(axis=1)]
    if len(samples) > params["max_samples"]:
        samples = np.sort(rng.choice(samples, params["max_samples"], replace=False))
    split = int(len(samples) * (1 - params["val_share"]))
    # samples are ordered by ticker then date; split by date instead.
    order = np.argsort(dates_of[samples], kind="stable")
    tr, va = samples[order[:split]], samples[order[split:]]

    def tensors(idx):
        y = np.nan_to_num(targets[idx].clip(-10, 10))
        mask = ((ends[idx] < cutoff) & np.isfinite(targets[idx])).astype(np.float32)
        return torch.from_numpy(y), torch.from_numpy(mask)

    net = build_net(params["hidden"], params["dropout"])
    opt = torch.optim.Adam(net.parameters(), lr=params["lr"])
    best, best_state, bad, history = float("inf"), None, 0, []
    yva, mva = tensors(va)
    for epoch in range(params["max_epochs"]):
        began = time.time()
        net.train()
        perm = rng.permutation(len(tr))
        total = 0.0
        for start in range(0, len(tr), params["batch"]):
            idx = tr[perm[start : start + params["batch"]]]
            y, mask = tensors(idx)
            opt.zero_grad()
            loss = lstm_loss(net(batch_x(x, idx)), y, mask, params["beat_loss_weight"])
            loss.backward()
            nn.utils.clip_grad_norm_(net.parameters(), 1.0)
            opt.step()
            total += loss.item() * len(idx)
        net.eval()
        with torch.no_grad():
            vl = sum(
                lstm_loss(
                    net(batch_x(x, va[s : s + 4096])),
                    yva[s : s + 4096],
                    mva[s : s + 4096],
                    params["beat_loss_weight"],
                ).item()
                * mva[s : s + 4096].sum().item()
                for s in range(0, len(va), 4096)
            ) / max(mva.sum().item(), 1)
        history.append(
            {"epoch": epoch + 1, "train": total / len(tr), "val": vl, "seconds": round(time.time() - began, 1)}
        )
        print(f"      epoch {epoch + 1}: train {total / len(tr):.4f} val {vl:.4f} ({time.time() - began:.0f}s)", flush=True)
        if vl < best - 1e-5:
            best, bad = vl, 0
            best_state = {k: v.clone() for k, v in net.state_dict().items()}
        else:
            bad += 1
            if bad >= params["patience"]:
                break
    net.load_state_dict(best_state)
    return net, {"train_samples": len(tr), "val_samples": len(va), "best_val": best, "epochs": history}


# --- LightGBM over the same buckets as 3.0.0 ----------------------------------


def fit_lgbm(train: pd.DataFrame, cols: list[str], params: dict):
    buckets = Buckets.fit(train["target"].to_numpy())
    model = lgb.LGBMClassifier(**params)
    model.fit(
        train[cols].to_numpy(dtype=np.float32),
        buckets.label(train["target"].to_numpy()),
        categorical_feature=[cols.index("sector")],
    )
    return model, buckets


def predict_lgbm(model, buckets: Buckets, rows: pd.DataFrame, cols: list[str]) -> pd.DataFrame:
    probs = full_probabilities(
        model.predict_proba(rows[cols].to_numpy(dtype=np.float32)), model.classes_, buckets.count
    )
    q = quantiles(probs, buckets, tsp.LEVELS)
    s = tsp.scale(rows, rows["horizon"]).to_numpy()[:, None]
    out = pd.DataFrame(q * s, columns=["low", "mid", "high"], index=rows.index)
    out["chance_beat"] = chance_above_zero(probs, buckets)
    return out


def lstm_pred(rows: pd.DataFrame) -> pd.DataFrame:
    s = tsp.scale(rows, rows["horizon"]).to_numpy()
    out = pd.DataFrame(index=rows.index)
    for name, col in zip(("low", "mid", "high"), LSTM_COLUMNS[:3], strict=True):
        out[name] = rows[col].to_numpy() * s
    out["chance_beat"] = rows["lstm_beat"].to_numpy()
    return out


def average(a: pd.DataFrame, b: pd.DataFrame) -> pd.DataFrame:
    return (a + b) / 2


def beat_call_scores(rows: pd.DataFrame, pred: pd.DataFrame) -> dict:
    """The beat-the-Nifty call (chance > 50%) as a classifier, per horizon
    group: precision, recall and F1 for "beat", for "lag", and macro."""
    groups = rows["horizon"].map(horizon_group).to_numpy()
    out = {}
    for label, _ in HORIZON_GROUPS:
        mask = groups == label
        if not mask.any():
            continue
        actual = rows["log_return"].to_numpy()[mask] > 0
        called = pred["chance_beat"].to_numpy()[mask] > 0.5
        scores = {}
        for name, a, c in (("beat", actual, called), ("lag", ~actual, ~called)):
            tp = int(np.sum(a & c))
            precision = tp / max(int(c.sum()), 1)
            recall = tp / max(int(a.sum()), 1)
            f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
            scores |= {f"{name}_precision": precision, f"{name}_recall": recall, f"{name}_f1": f1}
        scores["macro_f1"] = (scores["beat_f1"] + scores["lag_f1"]) / 2
        scores["share_called_beat"] = float(called.mean())
        out[label] = scores
    return out


# --- main ----------------------------------------------------------------------


MODELS = ("lgbm_full", "lgbm_same", "lstm", "ensemble", "stacked")
dates_of: np.ndarray  # stock-day dates as day numbers, set in main
FINAL_VERSION = "4.0.0"


def train_final(features, x, valid, targets, ends, day_index, lstm_params, lgbm_params, started) -> None:
    """The shipped ensemble: one LSTM and one LightGBM on all data, saved as
    model.joblib next to the walk-forward metrics.json, which gains the
    fields the prediction service reads (model_version, evaluation, data)."""
    metrics_path = OUT_DIR / "metrics.json"
    if not metrics_path.exists():
        sys.exit("Run the walk-forward test first (without --final)")
    print("Training the final LSTM on all data...", flush=True)
    candidates = np.flatnonzero(valid & (day_index % LSTM_STRIDE == 0))
    never = int(np.iinfo(np.int64).max)
    net, lstm_info = train_lstm(x, targets, ends, candidates, never, lstm_params, seed=42)

    print("Training the final LightGBM on all data...", flush=True)
    data = tsp.labelled_rows(features, tsp.BROAD_STRIDE, thin=True)
    data = data[tsp.KEEP_COLUMNS + FEATURE_COLUMNS]
    stocks = sorted(features["ticker"].unique().tolist())
    train, eligible = tsp.training_rows(data, data["train_row"])
    model, buckets = fit_lgbm(train, FEATURE_COLUMNS, lgbm_params)

    artifact = {
        "kind": "lstm_lightgbm_ensemble",
        "model": model,
        "bucket_edges": buckets.edges,
        "bucket_low": buckets.low,
        "bucket_high": buckets.high,
        "target": tsp.TARGET,
        "feature_columns": FEATURE_COLUMNS,
        "horizons": list(HORIZON_GRID),
        "version": FINAL_VERSION,
        "lstm_state": {k: v.detach().cpu() for k, v in net.state_dict().items()},
        "lstm_config": {"hidden": lstm_params["hidden"], "dropout": lstm_params["dropout"], "seq_len": SEQ_LEN},
    }
    joblib.dump(artifact, OUT_DIR / "model.joblib", compress=3)

    metrics = json.loads(metrics_path.read_text())
    metrics.update(
        {
            "model_version": FINAL_VERSION,
            "model": "Average of LightGBM (27 inputs) and an LSTM over the last 64 days",
            "evaluation": {
                "method": "Walk-forward by calendar year (see results.ensemble)",
                "test_years": metrics["test_years"],
                "overall": metrics["results"]["ensemble"],
            },
            "data": {"stocks": stocks, "stock_days": len(features)},
            "final_training": {
                "lstm": lstm_info,
                "lightgbm_rows": len(train),
                "lightgbm_eligible_rows": eligible,
                "trained_at": datetime.now(UTC).isoformat(timespec="seconds"),
                "seconds": round(time.time() - started),
            },
        }
    )
    metrics_path.write_text(json.dumps(metrics, indent=2))
    print(f"Saved {OUT_DIR / 'model.joblib'} ({FINAL_VERSION})", flush=True)


def main() -> None:
    global dates_of
    parser = argparse.ArgumentParser()
    parser.add_argument("--quick", action="store_true")
    parser.add_argument(
        "--final",
        action="store_true",
        help="train the shipped ensemble (4.0.0) on all data; run after the walk-forward test",
    )
    args = parser.parse_args()
    torch.set_num_threads(THREADS)
    test_years = tsp.TEST_YEARS[-2:] if args.quick else tsp.TEST_YEARS
    oof_start = 2022 if args.quick else OOF_START
    lstm_params = {**LSTM_PARAMS, "max_epochs": 2, "max_samples": 30_000} if args.quick else LSTM_PARAMS
    lgbm_params = {**LGBM_PARAMS, "n_estimators": 40} if args.quick else LGBM_PARAMS
    out_dir = OUT_DIR / ("quick" if args.quick else "")
    ckpt = out_dir / "checkpoints"
    ckpt.mkdir(parents=True, exist_ok=True)
    started = time.time()

    print("Loading prices and computing features...", flush=True)
    prices, market = tsp.load_data(False, "broad")
    features = compute_features(prices, market)
    del prices
    print(f"  {len(features):,} stock-days", flush=True)

    print("Building LSTM sequences and targets...", flush=True)
    x, valid = sequence_inputs(features)
    targets, ends = day_targets(features)
    dates_of = features["date"].to_numpy().astype("datetime64[D]").astype(np.int64)
    day_index = features["date"].rank(method="dense").astype(int).to_numpy()

    if args.final:
        train_final(features, x, valid, targets, ends, day_index, lstm_params, lgbm_params, started)
        return

    print("Labelling rows (same as 3.0.0)...", flush=True)
    data = tsp.labelled_rows(features, tsp.BROAD_STRIDE, thin=True)
    data = data[tsp.KEEP_COLUMNS + FEATURE_COLUMNS]
    floats = [c for c in FEATURE_COLUMNS if data[c].dtype == "float64"]
    data[floats] = data[floats].astype("float32")
    keys = features[["ticker", "date"]].reset_index(drop=True).reset_index().rename(columns={"index": "fidx"})
    data = data.merge(keys, on=["ticker", "date"], how="left")
    data["hidx"] = data["horizon"].map({h: k for k, h in enumerate(HORIZON_GRID)}).astype(int)
    stock_days = len(features)
    del features, keys
    gc.collect()
    print(f"  {len(data):,} labelled rows", flush=True)

    # --- walk-forward LSTM: out-of-sample predictions for every year from oof_start
    oof = np.full((stock_days, H, 4), np.nan, dtype=np.float32)
    lstm_folds = {}
    candidates = np.flatnonzero(valid & (day_index % LSTM_STRIDE == 0))
    years_of = (dates_of.astype("datetime64[D]").astype("datetime64[Y]").astype(int) + 1970)
    for year in range(oof_start, test_years[-1] + 1):
        saved = ckpt / f"lstm_{year}.npy"
        target_idx = np.flatnonzero(valid & (years_of == year))
        if saved.exists():
            oof[target_idx] = np.load(saved)
            lstm_folds[str(year)] = json.loads(saved.with_suffix(".json").read_text())
            print(f"  LSTM {year}: loaded from checkpoint", flush=True)
            continue
        cutoff = year_day(year)
        began = time.time()
        print(f"  LSTM for {year} (labels ending before {year})...", flush=True)
        net, info = train_lstm(
            x, targets, ends, candidates[dates_of[candidates] < cutoff], cutoff, lstm_params, seed=year
        )
        pred = predict_lstm(net, x, target_idx)
        oof[target_idx] = pred
        info["seconds"] = round(time.time() - began, 1)
        info["predicted_stock_days"] = len(target_idx)
        lstm_folds[str(year)] = info
        np.save(saved, pred)
        saved.with_suffix(".json").write_text(json.dumps(info))
        del net
        gc.collect()

    vals = oof[data["fidx"].to_numpy(), data["hidx"].to_numpy()]
    for k, col in enumerate(LSTM_COLUMNS):
        data[col] = vals[:, k]
    del oof, vals, x, targets, ends
    gc.collect()
    has_lstm = data["lstm_q50"].notna()

    # --- walk-forward over test years
    folds, tests, preds = {}, [], {m: [] for m in (*MODELS, "baseline")}
    for year in test_years:
        saved = ckpt / f"test_{year}.parquet"
        if saved.exists():
            frame = pd.read_parquet(saved)
            folds[str(year)] = json.loads(saved.with_suffix(".json").read_text())
            tests.append(frame[tsp.SCORED_COLUMNS])
            for m in preds:
                preds[m].append(frame[[f"{m}_{c}" for c in ("low", "mid", "high", "chance_beat")]].rename(columns=lambda c, m=m: c.removeprefix(f"{m}_")))
            print(f"  {year}: loaded from checkpoint", flush=True)
            continue
        start, end = pd.Timestamp(year, 1, 1), pd.Timestamp(year + 1, 1, 1)
        before = (data["label_end"] < start) & data["train_row"]
        window = before & has_lstm & (data["date"] >= pd.Timestamp(oof_start, 1, 1))
        test = data[(data["date"] >= start) & (data["date"] < end)]
        if test["lstm_q50"].isna().any():
            print(f"    note: {int(test['lstm_q50'].isna().sum())} test rows lack LSTM output; dropped for all models")
            test = test[test["lstm_q50"].notna()]
        info, year_preds = {}, {}
        for name, mask, cols in (
            ("lgbm_full", before, FEATURE_COLUMNS),
            ("lgbm_same", window, FEATURE_COLUMNS),
            ("stacked", window, STACKED_COLUMNS),
        ):
            began = time.time()
            train, eligible = tsp.training_rows(data, mask)
            model, buckets = fit_lgbm(train, cols, lgbm_params)
            year_preds[name] = predict_lgbm(model, buckets, test, cols)
            info[name] = {"train_rows": len(train), "eligible": eligible, "seconds": round(time.time() - began, 1)}
            if name == "lgbm_full":
                year_preds["baseline"] = tsp.baseline(train, test)
            if name == "stacked":
                gain = model.booster_.feature_importance("gain")
                info[name]["gain_share_lstm_inputs"] = float(gain[-len(LSTM_COLUMNS):].sum() / gain.sum())
            print(f"  {year} {name}: {len(train):,} rows, {info[name]['seconds']}s", flush=True)
            del model, train
            gc.collect()
        year_preds["lstm"] = lstm_pred(test)
        year_preds["ensemble"] = average(year_preds["lgbm_full"], year_preds["lstm"])
        info["test_rows"] = len(test)
        folds[str(year)] = info
        test = test[tsp.SCORED_COLUMNS]
        pd.concat([test, *(p.add_prefix(f"{m}_") for m, p in year_preds.items())], axis=1).to_parquet(saved)
        saved.with_suffix(".json").write_text(json.dumps(info))
        tests.append(test)
        for m in preds:
            preds[m].append(year_preds[m])

    all_tests = pd.concat(tests)
    pooled = {m: pd.concat(p) for m, p in preds.items()}
    results = {m: tsp.score_by_group(all_tests, pooled[m], pooled["baseline"]) for m in MODELS}
    for m in MODELS:
        for group, extra in beat_call_scores(all_tests, pooled[m]).items():
            results[m][group].update(extra)
    per_year = {}
    for year in test_years:
        in_year = (all_tests["date"].dt.year == year).to_numpy()
        per_year[str(year)] = {
            m: {
                g: {k: v[k] for k in ("pinball_loss", "brier", "rank_correlation", "call_accuracy")}
                for g, v in tsp.score_by_group(all_tests[in_year], pooled[m][in_year], pooled["baseline"][in_year]).items()
            }
            for m in MODELS
        }

    reference = None
    ref_path = ML_DIR / "models" / "stock_predictor" / "metrics.json"
    if ref_path.exists():
        ref = json.loads(ref_path.read_text())
        if ref.get("universe") == "broad":
            reference = {"model_version": ref["model_version"], "overall": ref["evaluation"]["overall"]}

    metrics = {
        "trained_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "quick_run": args.quick,
        "papers": [
            "Tian et al. 2022, J. Supercomputing, doi:10.1007/s11227-022-04326-5",
            "Huang 2025, AEMSS (Atlantis Press), LSTM-LightGBM fusion by stacking",
            "Yu et al. 2025, arXiv:2505.23084",
        ],
        "models": {
            "lgbm_full": "LightGBM, 27 inputs, all history (like 3.0.0)",
            "lgbm_same": f"LightGBM, 27 inputs, training rows from {oof_start} only",
            "lstm": f"LSTM alone over the last {SEQ_LEN} days, 7 daily channels",
            "ensemble": "average of lgbm_full and lstm ranges and chances",
            "stacked": f"LightGBM, 27 inputs + 4 out-of-sample LSTM outputs, rows from {oof_start}",
        },
        "lgbm_params": lgbm_params,
        "lstm_params": {**lstm_params, "seq_len": SEQ_LEN, "stride": LSTM_STRIDE, "oof_start": oof_start},
        "test_years": list(test_years),
        "stock_days": stock_days,
        "results": results,
        "baseline_volatility_only": {g: {k: v[k] for k in v if k.startswith("baseline_")} for g, v in results["lgbm_full"].items()},
        "per_year": per_year,
        "reference_shipped_model": reference,
        "folds": folds,
        "lstm_folds": lstm_folds,
        "seconds": round(time.time() - started),
    }
    # A rerun (e.g. to add a metric, reusing checkpoints) keeps what --final added.
    previous = json.loads((out_dir / "metrics.json").read_text()) if (out_dir / "metrics.json").exists() else {}
    if "final_training" in previous:
        for key in ("model_version", "model", "data", "final_training"):
            metrics[key] = previous[key]
        metrics["evaluation"] = {**previous["evaluation"], "overall": results["ensemble"]}
    (out_dir / "metrics.json").write_text(json.dumps(metrics, indent=2))

    for group in results["lgbm_full"]:
        print(f"\n{group}")
        print(f"  {'model':10} {'pinball':>9} {'range hit':>9} {'brier':>7} {'call':>6} {'rank corr':>9} {'top5-bot5':>9}")
        rows = [(m, results[m][group]) for m in MODELS]
        if reference and group in reference["overall"]:
            rows.append((f"ship {reference['model_version']}", reference["overall"][group]))
        for m, r in rows:
            print(
                f"  {m:10} {r['pinball_loss']:9.5f} {r['range_hit_rate']:9.1%} {r['brier']:7.4f}"
                f" {r['call_accuracy']:6.1%} {r['rank_correlation']:9.3f} {r['top5_minus_bottom5_pct']:8.2f}%"
            )
        b = results["lgbm_full"][group]
        print(f"  {'vol only':10} {b['baseline_pinball_loss']:9.5f} {b['baseline_range_hit_rate']:9.1%} {b['baseline_brier']:7.4f}")
    print(f"\nSaved to {out_dir} in {metrics['seconds']}s")


if __name__ == "__main__":
    main()
