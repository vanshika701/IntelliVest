"""Sector routes: precomputed Phase 6 rollups."""

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.deps import get_current_user_id
from app.schemas.sector import Sector, SectorArticle
from app.services import sector_service

router = APIRouter(prefix="/sectors", tags=["sectors"], dependencies=[Depends(get_current_user_id)])


@router.get("", response_model=list[Sector])
async def list_sectors():
    return await sector_service.list_sectors()


@router.get("/{sector}", response_model=Sector)
async def get_sector(sector: str):
    result = await sector_service.get_sector(sector)
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sector not found")
    return result


@router.get("/{sector}/news", response_model=list[SectorArticle])
async def get_sector_news(
    sector: str,
    exclude_ticker: str | None = Query(default=None, max_length=30),
    limit: int = Query(default=8, ge=1, le=30),
):
    result = await sector_service.sector_news(sector, exclude_ticker, limit)
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sector not found")
    return result
