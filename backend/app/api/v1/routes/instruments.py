"""Instrument routes — search across stocks/MFs/ETFs, detail, price history."""

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.deps import get_current_user_id
from app.schemas.instrument import InstrumentDetail, InstrumentSearchResponse, PriceHistory
from app.schemas.sentiment import InstrumentSentiment
from app.services.instrument_service import (
    DataProviderError,
    InstrumentNotFound,
    get_daily_history,
    get_instrument,
    get_intraday_history,
    search_instruments,
)
from app.services.sentiment_service import get_instrument_sentiment

router = APIRouter(prefix="/instruments", tags=["instruments"], dependencies=[Depends(get_current_user_id)])


def _not_found() -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Instrument not found")


def _provider_down(exc: Exception) -> HTTPException:
    return HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc) or "Data provider unavailable")


@router.get("/search", response_model=InstrumentSearchResponse)
async def search(q: str = Query(min_length=2, max_length=100), limit: int = Query(default=15, ge=1, le=25)):
    return await search_instruments(q, limit)


@router.get("/{instrument_id}", response_model=InstrumentDetail)
async def detail(instrument_id: str):
    try:
        return await get_instrument(instrument_id)
    except InstrumentNotFound:
        raise _not_found() from None
    except DataProviderError as exc:
        raise _provider_down(exc) from None


@router.get("/{instrument_id}/history", response_model=PriceHistory)
async def history(instrument_id: str):
    try:
        return await get_daily_history(instrument_id)
    except InstrumentNotFound:
        raise _not_found() from None
    except DataProviderError as exc:
        raise _provider_down(exc) from None


@router.get("/{instrument_id}/sentiment", response_model=InstrumentSentiment)
async def sentiment(instrument_id: str):
    try:
        return await get_instrument_sentiment(instrument_id)
    except InstrumentNotFound:
        raise _not_found() from None
    except DataProviderError as exc:
        raise _provider_down(exc) from None


@router.get("/{instrument_id}/intraday", response_model=PriceHistory)
async def intraday(instrument_id: str):
    try:
        return await get_intraday_history(instrument_id)
    except InstrumentNotFound:
        raise _not_found() from None
    except DataProviderError as exc:
        raise _provider_down(exc) from None
