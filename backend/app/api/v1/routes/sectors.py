"""Sector routes: precomputed Phase 6 rollups."""

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import get_current_user_id
from app.schemas.sector import Sector
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
