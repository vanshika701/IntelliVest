"""Instrument routes — search across stocks/MFs/ETFs, detail, price history."""

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.deps import get_current_user_id
from app.core.rate_limit import SlidingWindowRateLimiter
from app.schemas.instrument import InstrumentDetail, InstrumentSearchResponse, PriceHistory
from app.schemas.news_summary import NewsSummaries
from app.schemas.sentiment import InstrumentSentiment
from app.services.instrument_service import (
    DataProviderError,
    InstrumentNotFound,
    get_daily_history,
    get_instrument,
    get_intraday_history,
    search_instruments,
)
from app.services.news_summary_service import get_news_summaries
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


_summaries_limiter = SlidingWindowRateLimiter(max_requests=20, window_seconds=60)


def _rate_limit_summaries(user_id: str = Depends(get_current_user_id)) -> None:
    retry_after = _summaries_limiter.hit(user_id)
    if retry_after is not None:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many summary requests — try again shortly.",
            headers={"Retry-After": str(max(1, round(retry_after)))},
        )


@router.get(
    "/{instrument_id}/news-summaries",
    response_model=NewsSummaries,
    dependencies=[Depends(_rate_limit_summaries)],
)
async def news_summaries(instrument_id: str):
    try:
        return await get_news_summaries(instrument_id)
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
