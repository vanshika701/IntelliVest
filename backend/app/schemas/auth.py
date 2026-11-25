"""Pydantic schemas for authentication request/response payloads.

These are *not* database models — they define what the API accepts from
clients and what it sends back.  The data layer stores whatever it needs;
these schemas are the contract between the frontend and the route layer.
"""

import re
import unicodedata
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


def _plausible_name(name: str) -> str:
    """Letters of any script, plus spaces, dots, hyphens and apostrophes."""
    name = name.strip()
    if not name:
        raise ValueError("Enter your full name")
    letters = re.sub(r"[ .'\u2019-]", "", name)
    if not name[0].isalpha() or any(unicodedata.category(c)[0] not in "LM" for c in letters):
        raise ValueError("Name can only contain letters, spaces, dots, hyphens and apostrophes")
    return name


NewPassword = Annotated[str, Field(min_length=8, max_length=72), AfterValidator(_fits_bcrypt)]
FullName = Annotated[str, Field(min_length=1, max_length=120), AfterValidator(_plausible_name)]
BirthDate = Annotated[date, AfterValidator(_plausible_birth_date)]


class RegisterRequest(BaseModel):
    email: EmailStr
    password: NewPassword
    full_name: FullName
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
