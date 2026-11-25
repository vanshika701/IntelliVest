"""Service layer for user authentication.

Owns password hashing and JWT token logic — route handlers call this
service, never import bcrypt/jwt directly.
"""

import logging
from datetime import UTC, date, datetime, timedelta

import bcrypt
import jwt

from app.core.config import settings
from app.core.rate_limit import SlidingWindowRateLimiter
from app.data.user_repository import (
    create_user,
    find_user_by_email,
    find_user_by_id,
    set_date_of_birth_once,
    set_password,
)

logger = logging.getLogger(__name__)

# A date of birth is guessable, so attempts per email are few.
reset_limiter = SlidingWindowRateLimiter(max_requests=5, window_seconds=24 * 60 * 60)


class TooManyAttempts(Exception):
    pass


# ---------------------------------------------------------------------------
# Password hashing
# ---------------------------------------------------------------------------

def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode(), bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode(), hashed.encode())


# ---------------------------------------------------------------------------
# JWT tokens
# ---------------------------------------------------------------------------

def create_access_token(user_id: str) -> str:
    expire = datetime.now(UTC) + timedelta(minutes=settings.jwt_access_token_expire_minutes)
    payload = {"sub": user_id, "exp": expire}
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> str | None:
    """Return the user_id from a valid token, or None if invalid/expired."""
    try:
        payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
        return payload.get("sub")
    except jwt.PyJWTError:
        return None


# ---------------------------------------------------------------------------
# High-level auth operations (called by route handlers)
# ---------------------------------------------------------------------------

async def register_user(email: str, password: str, full_name: str, date_of_birth: date) -> dict:
    """Register a new user. Raises ValueError if email is already taken."""
    existing = await find_user_by_email(email)
    if existing:
        raise ValueError("Email already registered")

    hashed = hash_password(password)
    user_id = await create_user(email, hashed, full_name, date_of_birth)
    logger.info("User registered: %s (id=%s)", email, user_id)
    return {
        "id": user_id,
        "email": email.lower(),
        "full_name": full_name,
        "has_date_of_birth": True,
    }


async def authenticate_user(email: str, password: str) -> dict | None:
    """Verify credentials. Returns user dict on success, None on failure."""
    user = await find_user_by_email(email)
    if not user:
        return None
    if not verify_password(password, user["hashed_password"]):
        return None
    return {
        "id": str(user["_id"]),
        "email": user["email"],
        "full_name": user["full_name"],
    }


async def reset_password(email: str, date_of_birth: date, new_password: str) -> bool:
    """Set a new password if the email and date of birth match an account. The
    caller can't tell a wrong email, wrong date and missing date apart."""
    if reset_limiter.hit(email.lower()) is not None:
        raise TooManyAttempts
    user = await find_user_by_email(email)
    if not user or user.get("date_of_birth") != date_of_birth.isoformat():
        return False
    await set_password(str(user["_id"]), hash_password(new_password))
    logger.info("Password reset (id=%s)", user["_id"])
    return True


async def add_date_of_birth(user_id: str, date_of_birth: date) -> bool:
    return await set_date_of_birth_once(user_id, date_of_birth)


async def get_current_user_data(user_id: str) -> dict | None:
    """Look up a user by ID and return their public profile."""
    user = await find_user_by_id(user_id)
    if not user:
        return None
    return {
        "id": str(user["_id"]),
        "email": user["email"],
        "full_name": user["full_name"],
        "has_date_of_birth": bool(user.get("date_of_birth")),
    }
