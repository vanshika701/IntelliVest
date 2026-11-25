"""Pydantic schemas for authentication request/response payloads.

These are *not* database models — they define what the API accepts from
clients and what it sends back.  The data layer stores whatever it needs;
these schemas are the contract between the frontend and the route layer.
"""

from datetime import date
from typing import Annotated

from pydantic import AfterValidator, BaseModel, EmailStr, Field


def _fits_bcrypt(password: str) -> str:
    if len(password.encode()) > 72:  # bcrypt's limit
        raise ValueError("Password is too long (72 bytes at most)")
    return password


def _plausible_birth_date(day: date) -> date:
    if not date(1900, 1, 1) <= day < date.today():  # noqa: DTZ011 - a calendar day
        raise ValueError("Enter a valid date of birth")
    return day


NewPassword = Annotated[str, Field(min_length=8, max_length=72), AfterValidator(_fits_bcrypt)]
BirthDate = Annotated[date, AfterValidator(_plausible_birth_date)]


class RegisterRequest(BaseModel):
    email: EmailStr
    password: NewPassword
    full_name: str = Field(min_length=1, max_length=120)
    date_of_birth: BirthDate


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class ResetPasswordRequest(BaseModel):
    email: EmailStr
    date_of_birth: date
    new_password: NewPassword


class DateOfBirthRequest(BaseModel):
    date_of_birth: BirthDate


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserResponse(BaseModel):
    """Public-facing user representation — never includes the password hash
    or the date of birth, which is what verifies a password reset."""

    id: str
    email: str
    full_name: str
    has_date_of_birth: bool
