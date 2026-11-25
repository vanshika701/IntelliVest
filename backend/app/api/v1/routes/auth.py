"""Auth routes — register, login, and me (current user profile)."""

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import get_current_user_id
from app.schemas.auth import (
    DateOfBirthRequest,
    LoginRequest,
    RegisterRequest,
    ResetPasswordRequest,
    TokenResponse,
    UserResponse,
)
from app.services.auth_service import (
    TooManyAttempts,
    add_date_of_birth,
    authenticate_user,
    create_access_token,
    get_current_user_data,
    register_user,
    reset_password,
)

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register(body: RegisterRequest):
    try:
        user = await register_user(body.email, body.password, body.full_name, body.date_of_birth)
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


@router.post("/reset-password", status_code=status.HTTP_204_NO_CONTENT)
async def reset_password_route(body: ResetPasswordRequest) -> None:
    """Forgot password: the date of birth is the only check, for now."""
    try:
        done = await reset_password(body.email, body.date_of_birth, body.new_password)
    except TooManyAttempts as exc:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many attempts for this email. Try again tomorrow.",
        ) from exc
    if not done:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="That email and date of birth don't match an account.",
        )


@router.put("/date-of-birth", status_code=status.HTTP_204_NO_CONTENT)
async def set_date_of_birth(
    body: DateOfBirthRequest, user_id: str = Depends(get_current_user_id)
) -> None:
    """For accounts made before sign-up asked for it. Can be set only once."""
    if not await add_date_of_birth(user_id, body.date_of_birth):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Your date of birth is already set."
        )


@router.get("/me", response_model=UserResponse)
async def me(user_id: str = Depends(get_current_user_id)):
    user = await get_current_user_data(user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return user
