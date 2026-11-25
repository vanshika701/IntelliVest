"""Pydantic schemas for the mock invest flow (one-time orders and SIPs)."""

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.instrument import InstrumentType

InvestmentKind = Literal["one_time", "sip"]
InvestmentStatus = Literal["pending_payment", "completed", "pending_mandate", "active", "failed"]

MAX_AMOUNT = 10_000_000  # ₹1 crore per order — a sanity cap, not a regulatory limit


class InvestmentAccount(BaseModel):
    id: str
    label: str
    kind: Literal["folio", "demat"]
    supports: list[InstrumentType]
    is_demo: bool = True


class OneTimeOrderCreate(BaseModel):
    instrument_id: str = Field(min_length=3, max_length=40)
    amount: float = Field(gt=0, le=MAX_AMOUNT)
    account_id: str = Field(min_length=1, max_length=40)


class SipCreate(OneTimeOrderCreate):
    # 1–28 so every month has the date (no Feb 30th).
    day_of_month: int = Field(ge=1, le=28)


class PaymentResultIn(BaseModel):
    status: Literal["success", "failed"]
    reference: str | None = Field(default=None, max_length=100)
    failure_reason: str | None = Field(default=None, max_length=200)


class InvestmentResponse(BaseModel):
    id: str
    kind: InvestmentKind
    status: InvestmentStatus
    instrument_id: str
    instrument_name: str
    instrument_type: InstrumentType
    amount: float
    account_id: str
    account_label: str
    price_at_order: float | None = None
    estimated_units: float | None = None
    day_of_month: int | None = None
    next_installment_date: date | None = None
    payment_reference: str | None = None
    failure_reason: str | None = None
    is_mock: bool = True
    created_at: datetime
    updated_at: datetime


class Holding(BaseModel):
    instrument_id: str
    instrument_name: str
    instrument_type: InstrumentType
    invested: float
    current_value: float | None  # None when there is no price
    gain: float | None
    gain_pct: float | None


class Portfolio(BaseModel):
    """Totals cover only the holdings that could be valued."""

    invested: float
    current_value: float
    gain: float | None
    gain_pct: float | None
    unvalued_count: int
    holdings: list[Holding]
