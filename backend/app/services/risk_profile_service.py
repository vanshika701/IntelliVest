"""Phase 7 risk profile: score answers (risk_profile.py) and store them."""

from datetime import UTC, datetime

from app.data import risk_profile_repository as repo
from app.services.risk_profile import score_answers


async def get_risk_profile(user_id: str) -> dict | None:
    return await repo.get_risk_profile(user_id)


async def save_risk_profile(user_id: str, answers: dict[str, str]) -> dict:
    """Score and store the answers. The answers are kept alongside the
    result so profiles can be rescored if the questionnaire changes."""
    result = score_answers(answers)
    return await repo.upsert_risk_profile(
        user_id, {**result, "answers": answers, "updated_at": datetime.now(UTC)}
    )
