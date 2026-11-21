"""Sentiment routes — precomputed FinBERT news sentiment per stock."""

import asyncio

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.deps import get_current_user_id
from app.core.constants import STOCK_UNIVERSE
from app.schemas.sentiment import TickerSentimentSummary
from app.services.sentiment_service import summarize_ticker_sentiment

router = APIRouter(prefix="/sentiment", tags=["sentiment"])


@router.get("", response_model=list[TickerSentimentSummary])
async def get_universe_sentiment(
    days: int = Query(default=7, ge=1, le=90),
    _user_id: str = Depends(get_current_user_id),
):
    return await asyncio.gather(*(summarize_ticker_sentiment(t, days) for t in STOCK_UNIVERSE))


@router.get("/{ticker}", response_model=TickerSentimentSummary)
async def get_ticker_sentiment(
    ticker: str,
    days: int = Query(default=7, ge=1, le=90),
    top_n: int = Query(default=3, ge=1, le=20),
    _user_id: str = Depends(get_current_user_id),
):
    ticker = ticker.upper()
    if ticker not in STOCK_UNIVERSE:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ticker not tracked")
    return await summarize_ticker_sentiment(ticker, days, top_n)
