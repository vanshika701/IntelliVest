"""Pure scoring for the Phase 7 risk questionnaire. No I/O, so every rule
is unit-tested directly; the async service in risk_profile_service.py
handles storage.
"""

from app.core.risk_config import (
    PROFILE_BY_ID,
    PROFILE_CAPS,
    PROFILES,
    QUESTION_BY_ID,
    QUESTIONS,
    RISK_QUESTIONNAIRE_VERSION,
    TOLERANCE_GAP_NOTE_POINTS,
    Dimension,
    RiskProfile,
)

_PROFILE_ORDER = [p.id for p in PROFILES]


class InvalidAnswers(ValueError):
    """Answers that don't match the questionnaire."""


def validate_answers(answers: dict[str, str]) -> None:
    """Every question answered exactly once, with one of its own options."""
    missing = sorted(set(QUESTION_BY_ID) - set(answers))
    unknown = sorted(set(answers) - set(QUESTION_BY_ID))
    if missing or unknown:
        parts = []
        if missing:
            parts.append(f"missing answers: {', '.join(missing)}")
        if unknown:
            parts.append(f"unknown questions: {', '.join(unknown)}")
        raise InvalidAnswers("; ".join(parts))
    for question_id, option_id in answers.items():
        if option_id not in {o.id for o in QUESTION_BY_ID[question_id].options}:
            raise InvalidAnswers(f"'{option_id}' is not an option for {question_id}")


def _option_score(question_id: str, option_id: str) -> int:
    return next(o.score for o in QUESTION_BY_ID[question_id].options if o.id == option_id)


def dimension_score(answers: dict[str, str], dimension: Dimension) -> float:
    """Average answer score for one dimension, rescaled from 1-5 to 0-100."""
    scores = [_option_score(q.id, answers[q.id]) for q in QUESTIONS if q.dimension == dimension]
    average = sum(scores) / len(scores)
    return round((average - 1) / 4 * 100, 1)


def profile_for_score(score: float) -> RiskProfile:
    return [p for p in PROFILES if score >= p.min_score][-1]


def _lower(a: str, b: str) -> str:
    return min(a, b, key=_PROFILE_ORDER.index)


def score_answers(answers: dict[str, str]) -> dict:
    """Turn validated answers into a profile, with the reasons behind it."""
    validate_answers(answers)
    capacity = dimension_score(answers, "capacity")
    tolerance = dimension_score(answers, "tolerance")
    from_scores = profile_for_score(min(capacity, tolerance)).id

    profile_id = from_scores
    caps_applied = []
    for (question_id, option_id), cap in PROFILE_CAPS.items():
        if answers[question_id] == option_id and _lower(profile_id, cap) == cap != profile_id:
            profile_id = cap
            caps_applied.append(
                {"question": question_id, "answer": option_id, "max_profile": cap}
            )

    if capacity < tolerance:
        limited_by = "capacity"
    elif tolerance < capacity:
        limited_by = "tolerance"
    else:
        limited_by = "both"

    notes = []
    if tolerance - capacity >= TOLERANCE_GAP_NOTE_POINTS:
        notes.append(
            "You're comfortable with more risk than your situation can absorb right now, "
            "so the profile follows your situation. Building an emergency fund, reducing "
            "EMIs or investing for longer would raise it."
        )
    for cap in caps_applied:
        question = QUESTION_BY_ID[cap["question"]]
        label = next(o.label for o in question.options if o.id == cap["answer"])
        notes.append(
            f'Because you answered "{label}" to "{question.text}", the profile is capped at '
            f"{PROFILE_BY_ID[cap['max_profile']].label}."
        )

    profile = PROFILE_BY_ID[profile_id]
    return {
        "profile": profile.id,
        "label": profile.label,
        "description": profile.description,
        "capacity_score": capacity,
        "tolerance_score": tolerance,
        "limited_by": limited_by,
        "caps_applied": caps_applied,
        "notes": notes,
        "version": RISK_QUESTIONNAIRE_VERSION,
    }


def questionnaire() -> dict:
    """The questions and profiles, for the frontend to render."""
    return {
        "version": RISK_QUESTIONNAIRE_VERSION,
        "questions": [
            {
                "id": q.id,
                "dimension": q.dimension,
                "text": q.text,
                "options": [{"id": o.id, "label": o.label} for o in q.options],
            }
            for q in QUESTIONS
        ],
        "profiles": [
            {"id": p.id, "label": p.label, "description": p.description} for p in PROFILES
        ],
    }
