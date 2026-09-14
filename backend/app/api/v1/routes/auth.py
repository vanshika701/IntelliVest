"""Auth routes — register, login, and me (current user profile)."""

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import get_current_user_id
from app.schemas.auth import LoginRequest, RegisterRequest, TokenResponse, UserResponse
from app.services.auth_service import authenticate_user, create_access_token, get_current_user_data, register_user

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register(body: RegisterRequest):
    try:
        user = await register_user(body.email, body.password, body.full_name)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    return user


@router.post("/login", response_model=TokenResponse)
async def login(body: LoginRequest):
    user = await authenticate_user(body.email, body.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )
    token = create_access_token(user["id"])
    return {"access_token": token, "token_type": "bearer"}


@router.get("/me", response_model=UserResponse)
async def me(user_id: str = Depends(get_current_user_id)):
    user = await get_current_user_data(user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return user
