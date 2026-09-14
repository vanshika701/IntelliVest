"""FastAPI dependency for extracting the current authenticated user.

Route handlers declare `user_id: str = Depends(get_current_user_id)` in
their signature — FastAPI runs this dependency first, and the handler
only executes if the token is valid.
"""

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.services.auth_service import decode_access_token

_bearer_scheme = HTTPBearer()


async def get_current_user_id(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer_scheme),
) -> str:
    """Validate the Bearer token and return the user_id it encodes.

    Raises 401 if the token is missing, malformed, or expired.
    """
    user_id = decode_access_token(credentials.credentials)
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user_id
