"""Phase 7 route: the latest precomputed market statistics."""

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import get_current_user_id
from app.services.market_stats_service import get_latest_stats

router = APIRouter(
    prefix="/market-stats", tags=["market-stats"], dependencies=[Depends(get_current_user_id)]
)


@router.get("/latest")
async def latest():
    stats = await get_latest_stats()
    if stats is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Market statistics haven't been computed yet.",
        )
    return stats
