"""Pydantic schemas for instrument search and the instrument detail page."""

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel

InstrumentType = Literal["STOCK", "MF", "ETF"]


class InstrumentSearchResult(BaseModel):
    id: str
    name: str
    type: InstrumentType
    symbol: str
    subtitle: str | None = None


class InstrumentSearchResponse(BaseModel):
    query: str
    results: list[InstrumentSearchResult]
    # True when a provider failed and only some sources answered.
    partial: bool = False


class InstrumentStats(BaseModel):
    rating: float | None = None
    rating_source: str | None = None
    analyst_rating: str | None = None  # stocks: e.g. "Buy"
    analyst_count: int | None = None
    market_cap_crore: float | None = None  # stocks
    aum_crore: float | None = None  # funds, all plans together
    aum_period: str | None = None  # e.g. "July - September 2026"
    min_sip: float | None = None
    min_investment: float | None = None
    # Fields holding placeholder values rather than real data.
    placeholder_fields: list[str] = []
    source: str


class InstrumentSector(BaseModel):
    id: str
    name: str


class InstrumentDetail(BaseModel):
    id: str
    name: str
    type: InstrumentType
    symbol: str
    subtitle: str | None = None
    category: str | None = None
    sector: InstrumentSector | None = None  # stocks
    currency: str
    price: float | None = None
    price_date: date | None = None
    previous_price: float | None = None
    day_change: float | None = None
    day_change_pct: float | None = None
    # Stocks: set when the price is a (delayed) quote rather than a stored close.
    quote_fetched_at: datetime | None = None
    quote_delay_minutes: int | None = None
    market_open: bool = False
    supports_intraday: bool
    stats: InstrumentStats


class PricePoint(BaseModel):
    t: str  # ISO date (daily) or ISO datetime in UTC (intraday)
    v: float


class PriceHistory(BaseModel):
    interval: Literal["1d", "5m"]
    points: list[PricePoint]
