"""Instrument routes — search across stocks/MFs/ETFs, detail, price history."""

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.deps import get_current_user_id
from app.core.rate_limit import SlidingWindowRateLimiter
from app.schemas.instrument import InstrumentDetail, InstrumentSearchResponse, PriceHistory
from app.schemas.news_summary import NewsDigest
from app.schemas.prediction import StockPrediction
from app.schemas.sentiment import InstrumentSentiment
from app.services.instrument_service import (
    DataProviderError,
    InstrumentNotFound,
    get_daily_history,
    get_instrument,
    get_intraday_history,
    search_instruments,
)
from app.services.news_summary_service import get_news_digest
from app.services.prediction_service import PredictionUnavailable, get_prediction
from app.services.sentiment_service import UnknownSentimentModel, get_instrument_sentiment
from app.services.summarization.factory import UnknownSummarizer

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


_MODEL_QUERY = Query(default=None, max_length=120, description="Model key from GET /models; default if omitted")


@router.get("/{instrument_id}/sentiment", response_model=InstrumentSentiment)
async def sentiment(instrument_id: str, model: str | None = _MODEL_QUERY):
    try:
        return await get_instrument_sentiment(instrument_id, model)
    except UnknownSentimentModel as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from None
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
    "/{instrument_id}/news-summary",
    response_model=NewsDigest,
    dependencies=[Depends(_rate_limit_summaries)],
)
async def news_summary(
    instrument_id: str,
    model: str | None = _MODEL_QUERY,
    sentiment_model: str | None = Query(default=None, max_length=120),
):
    """One combined summary of the top 5 recent articles, plus the articles.
    `model` picks the summarizer, `sentiment_model` the article tags."""
    try:
        return await get_news_digest(instrument_id, model, sentiment_model)
    except (UnknownSummarizer, UnknownSentimentModel) as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from None
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


@router.get("/{instrument_id}/prediction", response_model=StockPrediction)
async def prediction(
    instrument_id: str,
    amount: int = Query(ge=1, le=730),
    unit: Literal["days", "months", "years"] = "days",
    model: str | None = _MODEL_QUERY,
):
    """Phase 4: the stored prediction for a horizon of `amount` `unit`."""
    try:
        return await get_prediction(instrument_id, amount, unit, model)
    except InstrumentNotFound:
        raise _not_found() from None
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from None
    except DataProviderError as exc:
        raise _provider_down(exc) from None
    except PredictionUnavailable:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No prediction available yet") from None
