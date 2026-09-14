"""Service layer for user authentication.

Owns password hashing and JWT token logic — route handlers call this
service, never import bcrypt/jwt directly.
"""

import logging
from datetime import UTC, datetime, timedelta

import bcrypt
import jwt

from app.core.config import settings
from app.data.user_repository import create_user, find_user_by_email, find_user_by_id

logger = logging.getLogger(__name__)


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

async def register_user(email: str, password: str, full_name: str) -> dict:
    """Register a new user. Raises ValueError if email is already taken."""
    existing = await find_user_by_email(email)
    if existing:
        raise ValueError("Email already registered")

    hashed = hash_password(password)
    user_id = await create_user(email, hashed, full_name)
    logger.info("User registered: %s (id=%s)", email, user_id)
    return {"id": user_id, "email": email.lower(), "full_name": full_name}


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


async def get_current_user_data(user_id: str) -> dict | None:
    """Look up a user by ID and return their public profile."""
    user = await find_user_by_id(user_id)
    if not user:
        return None
    return {
        "id": str(user["_id"]),
        "email": user["email"],
        "full_name": user["full_name"],
    }
