"""Phase 7 routes: create and read portfolio recommendations."""

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import get_current_user_id
from app.schemas.recommendation import RecommendationIn
from app.services import recommendation_service
from app.services.equity_optimizer import OptimizationError
from app.services.recommendation_service import GoalNotFound, RecommendationUnavailable

router = APIRouter(prefix="/recommendations", tags=["recommendations"])


@router.post("", status_code=status.HTTP_201_CREATED)
async def create(body: RecommendationIn, user_id: str = Depends(get_current_user_id)):
    try:
        return await recommendation_service.create_recommendation(user_id, **body.model_dump())
    except GoalNotFound:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Goal not found") from None
    except RecommendationUnavailable as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from None
    except OptimizationError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Couldn't build the stock part right now: {exc}",
        ) from None


@router.get("/latest")
async def latest(user_id: str = Depends(get_current_user_id)):
    recommendation = await recommendation_service.get_latest_recommendation(user_id)
    if recommendation is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No recommendation yet.")
    return recommendation
