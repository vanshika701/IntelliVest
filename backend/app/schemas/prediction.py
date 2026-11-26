"""Pydantic schemas for Phase 4 stock predictions."""

from datetime import date
from typing import Literal

from pydantic import BaseModel


class PredictionTestResult(BaseModel):
    """How the model did on past years it never trained on, for horizons
    like the one asked for."""

    horizon_group: str
    test_years: list[int]
    range_hit_rate: float  # share of real returns inside the range (aim: 0.8)
    direction_accuracy: float
    always_up_accuracy: float


class StockPrediction(BaseModel):
    instrument_id: str
    ticker: str
    amount: int
    unit: Literal["days", "months", "years"]
    trading_days: int
    as_of: date  # last close the model saw
    target_date: date
    last_close: float
    chance_up: float  # 0 to 1
    # 10th, 50th and 90th percentile of the return, in percent.
    low_pct: float
    mid_pct: float
    high_pct: float
    low_price: float
    mid_price: float
    high_price: float
    rank: int  # 1 = highest middle case among tracked stocks
    rank_of: int
    # False: not one of the 20 tracked stocks the model was tested on.
    tracked: bool
    model_version: str
    artifact_hash: str
    test_result: PredictionTestResult | None
