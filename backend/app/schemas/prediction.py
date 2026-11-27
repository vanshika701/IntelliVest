"""Pydantic schemas for Phase 4 stock predictions."""

from datetime import date
from typing import Literal

from pydantic import BaseModel


class PredictionTestResult(BaseModel):
    """How the model did on past years it never trained on, for horizons
    like the one asked for."""

    horizon_group: str
    # "tracked": the 20 tracked stocks; "all": every stock in the test set.
    tested_on: str
    stock_count: int  # stocks the model was trained and tested on
    test_years: list[int]
    range_hit_rate: float  # share of real results inside the range (aim: 0.8)
    call_accuracy: float  # beat/lag call (chance above or below 50%) right
    majority_call_accuracy: float  # always making the more common call
    beat_share: float  # share of test cases where the stock beat the Nifty


class StockPrediction(BaseModel):
    instrument_id: str
    ticker: str
    amount: int
    unit: Literal["days", "months", "years"]
    trading_days: int
    as_of: date  # last close the model saw
    target_date: date
    last_close: float
    chance_beat: float  # chance of beating the Nifty 50 over the horizon, 0 to 1
    # 10th, 50th and 90th percentile of the stock's result against the
    # Nifty, in percent: (1 + stock return) / (1 + Nifty return) - 1.
    low_pct: float
    mid_pct: float
    high_pct: float
    rank: int  # 1 = highest middle case among the stocks compared
    rank_of: int
    # False: not one of the 20 tracked stocks the model was tested on.
    tracked: bool
    model: str  # prediction model key, e.g. "lstm_lgbm"
    model_label: str
    model_version: str
    artifact_hash: str
    test_result: PredictionTestResult | None
