"""Pydantic schemas for the Phase 7 risk profile."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.services.risk_profile import InvalidAnswers, validate_answers

ProfileId = Literal[
    "conservative", "moderately_conservative", "moderate", "moderately_aggressive", "aggressive"
]


class RiskAnswersIn(BaseModel):
    # question id -> option id, e.g. {"horizon": "5_10y", ...}
    answers: dict[str, str] = Field(max_length=50)

    @field_validator("answers")
    @classmethod
    def _check_answers(cls, value: dict[str, str]) -> dict[str, str]:
        try:
            validate_answers(value)
        except InvalidAnswers as exc:
            raise ValueError(str(exc)) from None
        return value


class ProfileCap(BaseModel):
    question: str
    answer: str
    max_profile: ProfileId


class RiskProfileOut(BaseModel):
    profile: ProfileId
    label: str
    description: str
    capacity_score: float
    tolerance_score: float
    limited_by: Literal["capacity", "tolerance", "both"]
    caps_applied: list[ProfileCap]
    notes: list[str]
    version: str
    answers: dict[str, str]
    updated_at: datetime
