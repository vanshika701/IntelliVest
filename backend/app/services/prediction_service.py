"""Phase 4: daily stock predictions, stored and then read per request.

Since model 2.0.0 a prediction is about the stock against the Nifty 50:
the chance it beats the index over the horizon, and a range for how far
ahead or behind it finishes (excess log return at the 10th, 50th and 90th
percentile).

After prices update, `refresh_predictions` runs the trained model once for
every tracked stock and every horizon in HORIZON_GRID and stores the
results. Requests (`get_prediction`) only read stored rows and interpolate
between horizons; they never run the model.

Untracked NSE stocks (outside the 20) are predicted on their first request
from Yahoo prices, compared with the tracked stocks on the same day, and
stored the same way, so later requests that day only read.

The model comes from ml/train_stock_predictor.py. Without it the app still
runs; the prediction route just reports that no prediction exists yet.
"""

import asyncio
import hashlib
import json
import logging
import math
from datetime import UTC, datetime
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import yfinance as yf

from app.core.cache import MISSING, TTLCache
from app.core.config import settings
from app.core.constants import STOCK_UNIVERSE
from app.data import prediction_repository as repo
from app.data.prices_repository import get_daily_bars, get_newest_date
from app.services import stock_listing
from app.services.instrument_service import get_untracked_bars, parse_instrument_id
from app.services.prediction.distribution import (
    HIGH_Q,
    LOW_Q,
    MID_Q,
    Buckets,
    chance_above_zero,
    full_probabilities,
    quantiles,
)
from app.services.prediction.features import compute_features, scale, with_horizon
from app.services.prediction.horizon import (
    Forecast,
    Unit,
    horizon_group,
    interpolate,
    target_date,
    to_trading_days,
)

logger = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).resolve().parents[3]
MARKET_TICKERS = {"nifty": "^NSEI", "vix": "^INDIAVIX"}
# Long enough for the 252-day features plus the 200-day market average.
MARKET_PERIOD = "2y"
_market_cache = TTLCache(ttl_seconds=60 * 60, max_items=1)
# What the stored numbers mean. Rows from an older model (plain returns)
# are never served; the next refresh replaces them.
TARGET = "excess_log_return_vs_nifty"


class PredictionUnavailable(Exception):
    """No stored prediction for this instrument (not a tracked stock, or
    the model or the daily job hasn't run yet)."""


class Predictor:
    def __init__(self, artifact: dict, artifact_hash: str, metrics: dict | None) -> None:
        self.model = artifact["model"]
        self.buckets = Buckets(
            edges=np.asarray(artifact["bucket_edges"]),
            low=artifact["bucket_low"],
            high=artifact["bucket_high"],
        )
        self.feature_columns: list[str] = artifact["feature_columns"]
        self.horizons: list[int] = artifact["horizons"]
        self.version: str = artifact["version"]
        self.target: str = artifact.get("target", "log_return")
        self.artifact_hash = artifact_hash
        self.metrics = metrics if metrics and metrics.get("model_version") == self.version else None

    def forecast(self, rows: pd.DataFrame, horizon_days: int) -> pd.DataFrame:
        """Excess-return percentiles and chance of beating the Nifty per row."""
        rows = with_horizon(rows, horizon_days)
        raw = self.model.predict_proba(rows[self.feature_columns].to_numpy())
        probs = full_probabilities(raw, self.model.classes_, self.buckets.count)
        q = (
            quantiles(probs, self.buckets, (LOW_Q, MID_Q, HIGH_Q))
            * scale(rows, horizon_days).to_numpy()[:, None]
        )
        out = pd.DataFrame(q, columns=["low", "mid", "high"], index=rows.index)
        out["chance_beat"] = chance_above_zero(probs, self.buckets)
        return out

    def test_result(self, trading_days: int) -> dict | None:
        if not self.metrics:
            return None
        group = horizon_group(trading_days)
        scores = self.metrics["evaluation"]["overall"].get(group)
        if not scores:
            return None
        return {
            "horizon_group": group,
            "test_years": self.metrics["evaluation"]["test_years"],
            "range_hit_rate": scores["range_hit_rate"],
            "call_accuracy": scores["call_accuracy"],
            "majority_call_accuracy": scores["majority_call_accuracy"],
            "beat_share": scores["beat_share"],
        }


_predictor: Predictor | None = None
_predictor_mtime: float | None = None


def _model_path() -> Path:
    path = Path(settings.stock_predictor_path)
    return path if path.is_absolute() else _REPO_ROOT / path


def load_predictor() -> Predictor | None:
    """The trained model, reloaded when the file changes; None if missing."""
    global _predictor, _predictor_mtime
    path = _model_path()
    if not path.exists():
        return None
    mtime = path.stat().st_mtime
    if _predictor is None or mtime != _predictor_mtime:
        data = path.read_bytes()
        artifact = joblib.load(path)
        metrics_path = path.with_name("metrics.json")
        metrics = json.loads(metrics_path.read_text()) if metrics_path.exists() else None
        _predictor = Predictor(artifact, hashlib.sha256(data).hexdigest(), metrics)
        _predictor_mtime = mtime
        logger.info(
            "Loaded stock predictor %s (%s)", _predictor.version, _predictor.artifact_hash[:12]
        )
    return _predictor


def _fetch_market() -> pd.DataFrame:
    frames = []
    for column, ticker in MARKET_TICKERS.items():
        raw = (
            yf.Ticker(ticker)
            .history(period=MARKET_PERIOD, interval="1d", timeout=15)
            .dropna(subset=["Close"])
        )
        if raw.empty:
            raise RuntimeError(f"No market data for {ticker}")
        dates = pd.to_datetime([d.date() for d in raw.index])
        frames.append(pd.DataFrame({"date": dates, column: raw["Close"].to_numpy()}))
    return frames[0].merge(frames[1], on="date", how="inner")


def build_predictions(
    predictor: Predictor,
    bars: list[dict],
    market: pd.DataFrame,
    now: datetime,
    focus: str | None = None,
) -> list[dict]:
    """Prediction documents for each ticker's newest day, every horizon.

    With `focus`, only that ticker's documents are returned; the others in
    `bars` are there so its rank compares it with them on the same day."""
    prices = pd.DataFrame(bars)
    if prices.empty:
        return []
    features = compute_features(prices, market)
    if features.empty or (focus and focus not in set(features["ticker"])):
        return []
    latest = features.loc[features.groupby("ticker")["date"].idxmax()].reset_index(drop=True)
    # Cross-sectional ranks must compare stocks on the same day.
    if focus:
        day = latest.loc[latest["ticker"] == focus, "date"].iloc[0]
        latest = features[features["date"] == day].reset_index(drop=True)
    else:
        latest = latest[latest["date"] == latest["date"].max()].reset_index(drop=True)
    docs = []
    for h in predictor.horizons:
        result = predictor.forecast(latest, h)
        order = result["mid"].rank(ascending=False, method="first").astype(int)
        for i, row in latest.iterrows():
            docs.append(
                {
                    "ticker": row["ticker"],
                    "as_of": datetime(
                        row["date"].year, row["date"].month, row["date"].day, tzinfo=UTC
                    ),
                    "horizon_days": int(h),
                    "close": float(row["close"]),
                    "chance_beat": float(result.at[i, "chance_beat"]),
                    "low": float(result.at[i, "low"]),
                    "mid": float(result.at[i, "mid"]),
                    "high": float(result.at[i, "high"]),
                    "rank": int(order[i]),
                    "rank_of": len(latest),
                    "tracked": stock_listing.is_tracked(row["ticker"]),
                    "target": predictor.target,
                    "model_version": predictor.version,
                    "artifact_hash": predictor.artifact_hash,
                    "created_at": now,
                }
            )
    return [d for d in docs if d["ticker"] == focus] if focus else docs


async def refresh_predictions(now: datetime | None = None) -> int:
    """Predict every tracked stock from stored prices; returns rows stored."""
    predictor = load_predictor()
    if predictor is None:
        logger.warning("No stock predictor at %s; run ml/train_stock_predictor.py", _model_path())
        return 0
    bars = await get_daily_bars(STOCK_UNIVERSE)
    try:
        market = await asyncio.to_thread(_fetch_market)
    except Exception:
        logger.exception("Stock predictions skipped: market data unavailable")
        return 0
    docs = await asyncio.to_thread(
        build_predictions, predictor, bars, market, now or datetime.now(UTC)
    )
    await repo.replace_predictions(docs)
    logger.info("Stored %d stock predictions", len(docs))
    return len(docs)


async def refresh_predictions_if_stale() -> bool:
    """Run when stored predictions are older than the newest prices, or
    were made by a different model file. Cheap to call often."""
    predictor = load_predictor()
    if predictor is None:
        return False
    run, newest_price = await repo.get_latest_run(), await get_newest_date(STOCK_UNIVERSE)
    if newest_price is None:
        return False
    if (
        run
        and run["artifact_hash"] == predictor.artifact_hash
        and run["as_of"].date() >= newest_price.date()
    ):
        return False
    return await refresh_predictions() > 0


async def _market() -> pd.DataFrame:
    cached = _market_cache.get("market")
    if cached is MISSING:
        cached = await asyncio.to_thread(_fetch_market)
        _market_cache.set("market", cached)
    return cached


async def _predict_untracked(ticker: str) -> None:
    """Store today's prediction for an untracked stock if it isn't stored yet.
    Raises PredictionUnavailable when there is no model or too little history."""
    predictor = load_predictor()
    if predictor is None:
        raise PredictionUnavailable(ticker)
    bars = await get_untracked_bars(ticker)
    stored = await repo.get_latest_for_ticker(ticker)
    if (
        stored
        and stored[0]["artifact_hash"] == predictor.artifact_hash
        and stored[0]["as_of"].date() >= bars[-1]["date"].date()
    ):
        return
    try:
        market = await _market()
    except Exception as exc:
        logger.warning("Market data unavailable for %s prediction: %s", ticker, exc)
        raise PredictionUnavailable(ticker) from exc
    tracked = await get_daily_bars(STOCK_UNIVERSE)
    docs = await asyncio.to_thread(
        build_predictions, predictor, tracked + bars, market, datetime.now(UTC), ticker
    )
    if not docs:
        raise PredictionUnavailable(ticker)
    await repo.replace_predictions(docs)


def _pct(log_return: float) -> float:
    return round(math.expm1(log_return) * 100, 2)


async def get_prediction(instrument_id: str, amount: int, unit: Unit) -> dict:
    """The stored prediction for any horizon, interpolated between the
    stored ones. Raises ValueError for an out-of-range horizon."""
    kind, ticker = parse_instrument_id(instrument_id)
    if kind != "stock":
        raise PredictionUnavailable(instrument_id)
    trading_days = to_trading_days(amount, unit)
    if not stock_listing.is_tracked(ticker):
        await _predict_untracked(ticker)
    docs = await repo.get_latest_for_ticker(ticker)
    if not docs or docs[0].get("target") != TARGET:
        raise PredictionUnavailable(instrument_id)

    stored = {
        d["horizon_days"]: Forecast(d["chance_beat"], d["low"], d["mid"], d["high"]) for d in docs
    }
    forecast = interpolate(stored, trading_days)
    # Rank from the stored horizon nearest on a log scale.
    nearest = min(docs, key=lambda d: abs(math.log(d["horizon_days"]) - math.log(trading_days)))
    first = docs[0]
    close = first["close"]
    as_of = first["as_of"].date()
    predictor = load_predictor()
    test_result = (
        predictor.test_result(trading_days)
        if predictor and predictor.artifact_hash == first["artifact_hash"]
        else None
    )
    return {
        "instrument_id": instrument_id,
        "ticker": ticker,
        "amount": amount,
        "unit": unit,
        "trading_days": trading_days,
        "as_of": as_of,
        "target_date": target_date(as_of, amount, unit),
        "last_close": round(close, 2),
        "chance_beat": round(forecast.chance_beat, 4),
        "low_pct": _pct(forecast.low),
        "mid_pct": _pct(forecast.mid),
        "high_pct": _pct(forecast.high),
        "rank": nearest["rank"],
        "rank_of": nearest["rank_of"],
        "tracked": stock_listing.is_tracked(ticker),
        "model_version": first["model_version"],
        "artifact_hash": first["artifact_hash"],
        "test_result": test_result,
    }
