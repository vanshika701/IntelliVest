from fastapi import APIRouter

from app.services import health_service

router = APIRouter(prefix="/health", tags=["health"])


@router.get("")
async def get_health() -> dict[str, str]:
    return await health_service.get_health_status()
