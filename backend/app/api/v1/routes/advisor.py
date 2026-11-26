"""Phase 9 routes: build and read the user's advice."""

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import get_current_user_id
from app.core.advisor_config import ADVICE_REQUESTS_PER_MINUTE
from app.core.rate_limit import SlidingWindowRateLimiter
from app.services.advisor import service

router = APIRouter(prefix="/advisor", tags=["advisor"])

_limiter = SlidingWindowRateLimiter(max_requests=ADVICE_REQUESTS_PER_MINUTE, window_seconds=60)


def _rate_limit(user_id: str = Depends(get_current_user_id)) -> str:
    retry_after = _limiter.hit(user_id)
    if retry_after is not None:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many advice requests; try again shortly.",
            headers={"Retry-After": str(max(1, round(retry_after)))},
        )
    return user_id


@router.post("/advice", status_code=status.HTTP_201_CREATED)
async def create_advice(user_id: str = Depends(_rate_limit)):
    """Fresh advice from every module. Always succeeds: modules that fail
    are listed in `modules_unavailable` and the advice is marked partial."""
    return await service.create_advice(user_id)


@router.get("/advice/latest")
async def latest_advice(user_id: str = Depends(get_current_user_id)):
    advice = await service.get_latest_advice(user_id)
    if advice is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No advice yet.")
    return advice
