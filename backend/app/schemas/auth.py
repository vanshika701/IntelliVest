"""Pydantic schemas for authentication request/response payloads.

These are *not* database models — they define what the API accepts from
clients and what it sends back.  The data layer stores whatever it needs;
these schemas are the contract between the frontend and the route layer.
"""

from pydantic import BaseModel, EmailStr, Field


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    full_name: str = Field(min_length=1, max_length=120)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserResponse(BaseModel):
    """Public-facing user representation — never includes password hash."""

    id: str
    email: str
    full_name: str
