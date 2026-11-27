"""Phase 10 routes: status, wallet linking, AI trade tasks.

Every route except /status returns 404 while BLOCKCHAIN_ENABLED is false, and
none of them waits for the chain: tasks are queued for the worker.
"""

from fastapi import APIRouter, Depends, HTTPException, Response, status

from app.api.deps import get_current_user_id
from app.core.config import settings
from app.schemas.blockchain import (
    BlockchainStatus,
    ChallengeRequest,
    ChallengeResponse,
    TaskCreate,
    TaskResponse,
    VerifyRequest,
    WalletResponse,
)
from app.services.blockchain import task_service, wallet_service
from app.services.blockchain.status_service import blockchain_status

router = APIRouter(prefix="/blockchain", tags=["blockchain"])


def require_enabled() -> None:
    if not settings.blockchain_enabled:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Blockchain features are off")


enabled = [Depends(require_enabled)]


@router.get("/status", response_model=BlockchainStatus)
async def get_status():
    return blockchain_status()


@router.post("/wallet/challenge", response_model=ChallengeResponse, dependencies=enabled)
async def wallet_challenge(body: ChallengeRequest, user_id: str = Depends(get_current_user_id)):
    try:
        return await wallet_service.create_challenge(user_id, body.address)
    except wallet_service.WalletError as exc:
        raise HTTPException(exc.status, exc.detail) from None


@router.post("/wallet/verify", response_model=WalletResponse, dependencies=enabled)
async def wallet_verify(body: VerifyRequest, user_id: str = Depends(get_current_user_id)):
    try:
        return await wallet_service.verify_and_link(user_id, body.address, body.signature)
    except wallet_service.WalletError as exc:
        raise HTTPException(exc.status, exc.detail) from None


@router.get("/wallet", response_model=WalletResponse, dependencies=enabled)
async def get_wallet(user_id: str = Depends(get_current_user_id)):
    return await wallet_service.get_wallet(user_id)


@router.delete("/wallet", status_code=status.HTTP_204_NO_CONTENT, dependencies=enabled)
async def unlink_wallet(user_id: str = Depends(get_current_user_id)):
    if not await wallet_service.unlink(user_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No wallet linked")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/tasks",
    response_model=TaskResponse,
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=enabled,
)
async def create_task(body: TaskCreate, user_id: str = Depends(get_current_user_id)):
    try:
        return await task_service.create_task(user_id, body.fund, body.ticker, body.horizon_days)
    except task_service.TaskError as exc:
        raise HTTPException(exc.status, exc.detail) from None


@router.get("/tasks", response_model=list[TaskResponse], dependencies=enabled)
async def list_tasks(user_id: str = Depends(get_current_user_id)):
    return await task_service.list_tasks(user_id)


@router.get("/tasks/{task_id}", response_model=TaskResponse, dependencies=enabled)
async def get_task(task_id: str, user_id: str = Depends(get_current_user_id)):
    task = await task_service.get_task(user_id, task_id)
    if task is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Task not found")
    return task
