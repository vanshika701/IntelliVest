"""Phase 7 routes: risk questionnaire and the user's risk profile."""

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import get_current_user_id
from app.schemas.risk_profile import RiskAnswersIn, RiskProfileOut
from app.services import risk_profile_service
from app.services.risk_profile import questionnaire

router = APIRouter(prefix="/risk-profile", tags=["risk-profile"])


@router.get("/questions")
async def get_questions():
    """The questionnaire and the profiles it can produce (no login needed)."""
    return questionnaire()


@router.get("", response_model=RiskProfileOut)
async def get_risk_profile(user_id: str = Depends(get_current_user_id)):
    profile = await risk_profile_service.get_risk_profile(user_id)
    if profile is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Answer the risk questionnaire first.",
        )
    return profile


@router.put("", response_model=RiskProfileOut)
async def put_risk_profile(body: RiskAnswersIn, user_id: str = Depends(get_current_user_id)):
    return await risk_profile_service.save_risk_profile(user_id, body.answers)
