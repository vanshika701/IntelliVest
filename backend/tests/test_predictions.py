"""Phase 4 stock predictions: horizon maths, bucket distributions, features
without lookahead, the daily job and the route."""

from datetime import UTC, date, datetime

import numpy as np
import pandas as pd
import pytest

from app.core.config import settings
from app.data import prediction_repository
from app.data.collections import get_stock_predictions_collection
from app.services import prediction_service
from app.services.prediction import sequence
from app.services.prediction.distribution import Buckets, chance_above_zero, quantiles
from app.services.prediction.features import FEATURE_COLUMNS, MIN_HISTORY, compute_features
from app.services.prediction.horizon import (
    HORIZON_GRID,
    Forecast,
    horizon_group,
    interpolate,
    target_date,
    to_trading_days,
)

AS_OF = datetime(2026, 11, 26, tzinfo=UTC)


# --- horizons ---------------------------------------------------------------


def test_units_convert_to_trading_days() -> None:
    assert to_trading_days(1, "days") == 1
    assert to_trading_days(7, "days") == 5
    assert to_trading_days(730, "days") == 504
    assert to_trading_days(3, "months") == 63
    assert to_trading_days(2, "years") == 504
    for amount, unit in [(0, "days"), (731, "days"), (25, "months"), (3, "years")]:
        with pytest.raises(ValueError):
            to_trading_days(amount, unit)


def test_target_date_uses_calendar_units() -> None:
    assert target_date(date(2026, 1, 31), 1, "months") == date(2026, 2, 28)
    assert target_date(date(2026, 11, 26), 7, "days") == date(2026, 12, 3)
    assert target_date(date(2024, 2, 29), 1, "years") == date(2025, 2, 28)


def test_horizon_groups_cover_the_grid() -> None:
    assert horizon_group(1) == "Up to 1 week"
    assert horizon_group(21) == "1 week to 1 month"
    assert horizon_group(504) == "6 months to 2 years"


def test_interpolation_between_stored_horizons() -> None:
    stored = {5: Forecast(0.5, -0.04, 0.0, 0.04), 20: Forecast(0.6, -0.08, 0.02, 0.10)}
    assert interpolate(stored, 5) == stored[5]
    middle = interpolate(stored, 10)  # halfway on a log scale
    assert middle.chance_beat == pytest.approx(0.55) and middle.high == pytest.approx(0.07)
    assert interpolate(stored, 1) == stored[5] and interpolate(stored, 100) == stored[20]


# --- distributions ----------------------------------------------------------


def test_buckets_always_have_an_edge_at_zero() -> None:
    buckets = Buckets.fit(np.random.default_rng(0).normal(0.3, 1, 5000))
    assert 0.0 in buckets.edges and np.all(np.diff(buckets.edges) > 0)
    assert buckets.low < buckets.edges[0] and buckets.high > buckets.edges[-1]
    assert list(buckets.label(np.array([buckets.low, 0.0, buckets.high]))) == [
        0,
        list(buckets.edges).index(0.0) + 1,
        buckets.count - 1,
    ]


def test_quantiles_and_chance_above_zero_from_bucket_probabilities() -> None:
    buckets = Buckets(edges=np.array([-1.0, 0.0, 1.0]), low=-2.0, high=2.0)
    uniform = np.full((1, 4), 0.25)  # flat density from -2 to 2
    assert quantiles(uniform, buckets, (0.1, 0.5, 0.9))[0] == pytest.approx([-1.6, 0.0, 1.6])
    assert chance_above_zero(uniform, buckets)[0] == pytest.approx(0.5)
    # An empty bucket doesn't break the inverse.
    skewed = np.array([[0.0, 0.2, 0.3, 0.5]])
    assert chance_above_zero(skewed, buckets)[0] == pytest.approx(0.8)
    assert quantiles(skewed, buckets, (0.1,))[0][0] == pytest.approx(-0.5)


# --- features ---------------------------------------------------------------


def synthetic(days: int = 400, tickers: tuple[str, ...] = ("TCS.NS", "INFY.NS"), seed: int = 1):
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range("2024-01-01", periods=days)
    prices = pd.concat(
        [
            pd.DataFrame(
                {
                    "ticker": t,
                    "date": dates,
                    "close": 100 * np.exp(np.cumsum(rng.normal(0, 0.015, days))),
                    "volume": rng.integers(1_000, 5_000, days),
                }
            )
            for t in tickers
        ]
    )
    market = pd.DataFrame(
        {
            "date": dates,
            "nifty": 20_000 * np.exp(np.cumsum(rng.normal(0, 0.01, days))),
            "vix": 15 + rng.random(days),
        }
    )
    return prices, market


def test_features_never_look_ahead() -> None:
    prices, market = synthetic()
    cutoff = prices["date"].unique()[300]
    full = compute_features(prices, market)
    changed = prices.copy()
    changed.loc[changed["date"] > cutoff, "close"] *= 3  # rewrite the future
    later = compute_features(changed, market)
    cols = [c for c in FEATURE_COLUMNS if c != "log_horizon"]
    before = full[full["date"] <= cutoff][cols].reset_index(drop=True)
    pd.testing.assert_frame_equal(
        before, later[later["date"] <= cutoff][cols].reset_index(drop=True)
    )


def test_data_break_restarts_history() -> None:
    prices, market = synthetic(tickers=("TCS.NS",))
    jump = prices["date"].unique()[200]
    prices.loc[prices["date"] >= jump, "close"] /= 2  # unadjusted split
    features = compute_features(prices, market)
    assert features["segment"].max() == 1
    after = features[features["segment"] == 1]
    assert after["date"].min() == prices["date"].unique()[200 + MIN_HISTORY - 1]
    assert (features["ret_1"].abs() < 0.2).all()


# --- daily job and route ----------------------------------------------------


class FlatModel:
    """Stand-in model: the same uniform bucket distribution for every row."""

    classes_ = np.arange(4)

    def predict_proba(self, rows: np.ndarray) -> np.ndarray:
        return np.full((len(rows), 4), 0.25)


def fake_predictor(model: str | None = None) -> prediction_service.Predictor:
    artifact = {
        "model": FlatModel(),
        "bucket_edges": [-1.0, 0.0, 1.0],
        "bucket_low": -2.0,
        "bucket_high": 2.0,
        "feature_columns": FEATURE_COLUMNS,
        "horizons": [1, 5, 21],
        "version": "test",
        "target": prediction_service.TARGET,
    }
    return prediction_service.Predictor(artifact, "hash", None, model or settings.prediction_model)


def test_build_predictions_covers_every_stock_and_horizon() -> None:
    prices, market = synthetic(tickers=("TCS.NS", "INFY.NS", "WIPRO.NS"))
    docs = prediction_service.build_predictions(
        fake_predictor(), prices.to_dict("records"), market, AS_OF
    )
    assert len(docs) == 3 * 3
    assert {d["horizon_days"] for d in docs} == {1, 5, 21}
    for h in (1, 5, 21):
        assert sorted(d["rank"] for d in docs if d["horizon_days"] == h) == [1, 2, 3]
    assert all(d["chance_beat"] == pytest.approx(0.5) and d["low"] < 0 < d["high"] for d in docs)
    assert docs[0]["as_of"] == datetime(*prices["date"].max().timetuple()[:3], tzinfo=UTC)


def stored_docs(model: str | None = None) -> list[dict]:
    return [
        {
            "ticker": "TCS.NS",
            "as_of": AS_OF,
            "horizon_days": h,
            "model": model or settings.prediction_model,
            "close": 4000.0,
            "chance_beat": 0.5 + h / 1000,
            "target": prediction_service.TARGET,
            "low": -0.01 * h**0.5,
            "mid": 0.001 * h,
            "high": 0.012 * h**0.5,
            "rank": 3,
            "rank_of": 20,
            "model_version": "test",
            "artifact_hash": "hash",
            "created_at": AS_OF,
        }
        for h in HORIZON_GRID
    ]


def test_prediction_route(client, auth_headers, monkeypatch) -> None:
    monkeypatch.setattr(prediction_service, "load_predictor", lambda *_: None)
    url = "/api/v1/instruments/stock-TCS.NS/prediction"
    assert client.get(f"{url}?amount=7", headers=auth_headers).status_code == 404  # nothing stored
    client.portal.call(prediction_repository.replace_predictions, stored_docs())

    body = client.get(f"{url}?amount=7&unit=days", headers=auth_headers).json()
    assert body["trading_days"] == 5 and body["target_date"] == "2026-12-03"
    assert body["chance_beat"] == pytest.approx(0.505)
    assert body["low_pct"] < body["mid_pct"] < body["high_pct"]
    assert body["mid_pct"] == pytest.approx(np.expm1(0.005) * 100, abs=0.01)
    assert body["rank"] == 3 and body["test_result"] is None

    years = client.get(f"{url}?amount=2&unit=years", headers=auth_headers).json()
    assert years["trading_days"] == 504 and years["target_date"] == "2028-11-26"
    assert client.get(f"{url}?amount=3&unit=years", headers=auth_headers).status_code == 422
    assert client.get(f"{url}?amount=0", headers=auth_headers).status_code == 422
    mf = client.get("/api/v1/instruments/mf-111954/prediction?amount=7", headers=auth_headers)
    assert mf.status_code == 404
    assert client.get(f"{url}?amount=7").status_code == 401


async def test_refresh_without_a_model_does_nothing(mongo_test_db, monkeypatch) -> None:
    monkeypatch.setattr(prediction_service, "load_predictor", lambda *_: None)
    assert await prediction_service.refresh_predictions() == 0
    assert await prediction_service.refresh_predictions_if_stale() is False
    assert await prediction_repository.latest_as_of() is None


# --- untracked NSE stocks ---------------------------------------------------


def test_untracked_prediction_is_made_on_demand_and_then_read(
    client, auth_headers, monkeypatch
) -> None:
    prices, market = synthetic(tickers=("TCS.NS", "COALINDIA.NS"))
    rows = prices.to_dict("records")
    coal = [
        {**r, "date": datetime(*r["date"].timetuple()[:3], tzinfo=UTC)}
        for r in rows
        if r["ticker"] == "COALINDIA.NS"
    ]
    tracked = [r for r in rows if r["ticker"] == "TCS.NS"]
    calls = []

    async def bars(ticker):
        calls.append(ticker)
        return coal

    async def stored_bars(_tickers):
        return tracked

    async def fake_market():
        return market

    monkeypatch.setattr(prediction_service, "load_predictor", fake_predictor)
    monkeypatch.setattr(prediction_service, "get_untracked_bars", bars)
    monkeypatch.setattr(prediction_service, "get_daily_bars", stored_bars)
    monkeypatch.setattr(prediction_service, "_market", fake_market)

    url = "/api/v1/instruments/stock-COALINDIA.NS/prediction?amount=7"
    first = client.get(url, headers=auth_headers).json()
    assert first["tracked"] is False and first["rank_of"] == 2
    assert first["as_of"] == coal[-1]["date"].date().isoformat()
    assert client.get(url, headers=auth_headers).json() == first  # second read: stored, not rebuilt
    run = client.portal.call(prediction_repository.get_latest_run)
    assert run is None  # untracked rows never count as the scheduled run


def test_rows_from_an_older_model_are_not_served(client, auth_headers, monkeypatch) -> None:
    monkeypatch.setattr(prediction_service, "load_predictor", lambda *_: None)
    old = [{k: v for k, v in d.items() if k != "target"} for d in stored_docs()]
    client.portal.call(prediction_repository.replace_predictions, old)
    url = "/api/v1/instruments/stock-TCS.NS/prediction?amount=7"
    assert client.get(url, headers=auth_headers).status_code == 404


def test_test_results_come_from_the_matching_stock_pool() -> None:
    scores = {
        "range_hit_rate": 0.8,
        "call_accuracy": 0.5,
        "majority_call_accuracy": 0.52,
        "beat_share": 0.48,
    }
    metrics = {
        "model_version": "test",
        "data": {"stocks": ["A"] * 173},
        "evaluation": {
            "test_years": [2020, 2025],
            "overall": {"Up to 1 week": scores},
            "tracked_stocks_only": {"Up to 1 week": {**scores, "range_hit_rate": 0.86}},
        },
    }
    predictor = fake_predictor()
    predictor.metrics = metrics
    tracked = predictor.test_result(5, tracked=True)
    untracked = predictor.test_result(5, tracked=False)
    assert (tracked["tested_on"], tracked["range_hit_rate"]) == ("tracked", 0.86)
    assert (untracked["tested_on"], untracked["range_hit_rate"], untracked["stock_count"]) == (
        "all",
        0.8,
        173,
    )
    assert predictor.test_result(504, tracked=True) is None  # no results for that horizon


# --- choosing a model -----------------------------------------------------------


def test_ensemble_averages_the_tree_and_lstm_forecasts() -> None:
    """With an LSTM, each forecast is the mean of the tree model's and the
    LSTM's (a zeroed LSTM says: median 0, low/high -/+softplus(0), 50%)."""
    import torch

    prices, market = synthetic(tickers=("TCS.NS", "INFY.NS", "WIPRO.NS"))
    features = compute_features(prices, market)
    latest = features[features["date"] == features["date"].max()]
    predictor = fake_predictor("lstm_lgbm")
    trees = predictor.forecast_all(latest, features)
    net = sequence.build_net()
    with torch.no_grad():
        for param in net.parameters():
            param.zero_()
    predictor.lstm = net
    both = predictor.forecast_all(latest, features)
    edge = float(np.log(2))  # softplus(0)
    for h in (1, 21):
        s = (latest["vol_63"] * np.sqrt(h)).to_numpy()
        np.testing.assert_allclose(both[h]["low"], (trees[h]["low"] - edge * s) / 2, rtol=1e-5)
        np.testing.assert_allclose(both[h]["mid"], trees[h]["mid"] / 2, rtol=1e-5, atol=1e-9)
        np.testing.assert_allclose(both[h]["chance_beat"], (trees[h]["chance_beat"] + 0.5) / 2, rtol=1e-5)


def test_prediction_route_serves_the_chosen_model(client, auth_headers, monkeypatch) -> None:
    monkeypatch.setattr(prediction_service, "load_predictor", lambda *_: None)
    lgbm = [{**d, "chance_beat": 0.9} for d in stored_docs("lgbm")]
    client.portal.call(prediction_repository.replace_predictions, stored_docs() + lgbm)
    url = "/api/v1/instruments/stock-TCS.NS/prediction?amount=7"

    default = client.get(url, headers=auth_headers).json()
    chosen = client.get(f"{url}&model=lgbm", headers=auth_headers).json()
    assert (default["model"], default["model_label"]) == ("lstm_lgbm", "LSTM + LightGBM")
    assert (chosen["model"], chosen["chance_beat"]) == ("lgbm", 0.9)
    assert client.get(f"{url}&model=nope", headers=auth_headers).status_code == 422

    catalog = client.get("/api/v1/models", headers=auth_headers).json()
    assert [m["key"] for m in catalog["prediction"]] == ["lstm_lgbm", "lgbm"]
    assert [m["default"] for m in catalog["prediction"]] == [True, False]
    assert sum(m["default"] for m in catalog["sentiment"]) == 1
    assert sum(m["default"] for m in catalog["summarizer"]) == 1


async def test_rows_from_before_model_choice_become_lightgbm_rows(mongo_test_db) -> None:
    """Old rows (no `model`, old unique index) are labelled LightGBM's, and
    the new index lets both models store the same stock, day and horizon."""
    from app.data.indexes import ensure_indexes

    collection = get_stock_predictions_collection()
    await collection.create_index(
        [("ticker", 1), ("as_of", -1), ("horizon_days", 1)], name="uniq_ticker_asof_horizon", unique=True
    )
    await collection.insert_many([{k: v for k, v in d.items() if k != "model"} for d in stored_docs()])

    await ensure_indexes()

    assert "uniq_ticker_asof_horizon" not in await collection.index_information()
    assert len(await prediction_repository.get_latest_for_ticker("TCS.NS", "lgbm")) == len(HORIZON_GRID)
    await prediction_repository.replace_predictions(stored_docs("lstm_lgbm"))
    assert len(await prediction_repository.get_latest_for_ticker("TCS.NS", "lstm_lgbm")) == len(HORIZON_GRID)
