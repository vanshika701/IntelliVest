"""Request schema for Phase 7 recommendations. The response is the stored
recommendation document (see services/recommendation.py)."""

from pydantic import BaseModel, Field, model_validator

from app.core.budget_config import MAX_GOAL_HORIZON_MONTHS

_MAX_AMOUNT = 1e10  # ₹1,000 crore: catches typos, not a real-world limit


class RecommendationIn(BaseModel):
    # Either a horizon, or a saved Phase 8 goal whose horizon is used.
    horizon_months: int | None = Field(default=None, ge=1, le=MAX_GOAL_HORIZON_MONTHS)
    goal_id: str | None = Field(default=None, min_length=1, max_length=64)
    lump_sum: float = Field(default=0, ge=0, le=_MAX_AMOUNT)
    monthly_sip: float = Field(default=0, ge=0, le=_MAX_AMOUNT)
    use_sentiment: bool = True

    @model_validator(mode="after")
    def _check(self) -> "RecommendationIn":
        if (self.horizon_months is None) == (self.goal_id is None):
            raise ValueError("Give either horizon_months or goal_id, not both")
        if self.lump_sum + self.monthly_sip < 1:
            raise ValueError("Give a one-time amount, a monthly amount, or both")
        return self
