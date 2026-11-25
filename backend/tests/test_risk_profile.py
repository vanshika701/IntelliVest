"""Phase 7 risk profile: scoring rules (pure) and the API (real HTTP + DB)."""

from itertools import product

import pytest
from fastapi.testclient import TestClient

from app.core.risk_config import PROFILE_CAPS, PROFILES, QUESTIONS
from app.services.risk_profile import (
    InvalidAnswers,
    dimension_score,
    profile_for_score,
    score_answers,
    validate_answers,
)

ORDER = [p.id for p in PROFILES]


def answers_with(score_index: int, **overrides: str) -> dict[str, str]:
    """Every question answered with its option at `score_index` (clamped)."""
    answers = {q.id: q.options[min(score_index, len(q.options) - 1)].id for q in QUESTIONS}
    return {**answers, **overrides}


LOWEST = answers_with(0)
HIGHEST = {q.id: q.options[-1].id for q in QUESTIONS}


def test_config_is_well_formed() -> None:
    assert len({q.id for q in QUESTIONS}) == len(QUESTIONS)
    assert {q.dimension for q in QUESTIONS} == {"capacity", "tolerance"}
    for q in QUESTIONS:
        scores = [o.score for o in q.options]
        assert len({o.id for o in q.options}) == len(q.options)
        # Each question must span the whole scale, in increasing order.
        assert scores == sorted(scores) and scores[0] == 1 and scores[-1] == 5
    assert [p.min_score for p in PROFILES] == sorted(p.min_score for p in PROFILES)
    assert PROFILES[0].min_score == 0
    for (question_id, option_id), cap in PROFILE_CAPS.items():
        question = next(q for q in QUESTIONS if q.id == question_id)
        assert option_id in {o.id for o in question.options}
        assert cap in ORDER


def test_extremes() -> None:
    low, high = score_answers(LOWEST), score_answers(HIGHEST)
    assert (low["capacity_score"], low["tolerance_score"]) == (0, 0)
    assert (high["capacity_score"], high["tolerance_score"]) == (100, 100)
    assert low["profile"] == "conservative"
    assert high["profile"] == "aggressive"
    assert high["limited_by"] == "both" and high["notes"] == []


@pytest.mark.parametrize(
    ("score", "profile"),
    [(0, "conservative"), (19.9, "conservative"), (20, "moderately_conservative"),
     (40, "moderate"), (60, "moderately_aggressive"), (79.9, "moderately_aggressive"),
     (80, "aggressive"), (100, "aggressive")],
)
def test_band_edges(score: float, profile: str) -> None:
    assert profile_for_score(score).id == profile


def test_capacity_limits_an_eager_investor() -> None:
    capacity_ids = {q.id for q in QUESTIONS if q.dimension == "capacity"}
    # Keen attitude, weak situation (but no cap-triggering answers).
    answers = {
        q.id: (q.options[1].id if q.id in capacity_ids else q.options[-1].id) for q in QUESTIONS
    }
    result = score_answers(answers)
    assert result["limited_by"] == "capacity"
    assert result["tolerance_score"] == 100
    assert result["profile"] == profile_for_score(result["capacity_score"]).id
    assert any("situation" in note for note in result["notes"])


def test_tolerance_limits_a_cautious_investor() -> None:
    tolerance_ids = {q.id for q in QUESTIONS if q.dimension == "tolerance"}
    answers = {
        q.id: (q.options[0].id if q.id in tolerance_ids else q.options[-1].id) for q in QUESTIONS
    }
    result = score_answers(answers)
    assert result["limited_by"] == "tolerance"
    assert result["profile"] == "conservative"
    assert result["notes"] == []


def test_caps_override_high_scores() -> None:
    short = score_answers({**HIGHEST, "horizon": "under_1y"})
    assert short["profile"] == "conservative"
    assert short["caps_applied"] == [
        {"question": "horizon", "answer": "under_1y", "max_profile": "conservative"}
    ]
    no_buffer = score_answers({**HIGHEST, "emergency_fund": "none"})
    assert no_buffer["profile"] == "moderately_conservative"
    assert any("capped" in note for note in no_buffer["notes"])


def test_cap_is_not_reported_when_scores_are_already_lower() -> None:
    result = score_answers({**LOWEST, "emergency_fund": "none"})
    assert result["profile"] == "conservative"
    assert result["caps_applied"] == []


def test_every_combination_respects_the_rules() -> None:
    """All 200,000 possible answer sets: the profile is never riskier than
    the lower score allows, and every cap holds."""
    option_lists = [[o.id for o in q.options] for q in QUESTIONS]
    for combo in product(*option_lists):
        answers = dict(zip((q.id for q in QUESTIONS), combo, strict=True))
        result = score_answers(answers)
        lower = min(result["capacity_score"], result["tolerance_score"])
        assert 0 <= lower <= 100
        assert ORDER.index(result["profile"]) <= ORDER.index(profile_for_score(lower).id)
        for (question_id, option_id), cap in PROFILE_CAPS.items():
            if answers[question_id] == option_id:
                assert ORDER.index(result["profile"]) <= ORDER.index(cap)


@pytest.mark.parametrize(
    ("answers", "message"),
    [
        ({k: v for k, v in HIGHEST.items() if k != "horizon"}, "missing answers: horizon"),
        ({**HIGHEST, "shoe_size": "9"}, "unknown questions: shoe_size"),
        ({**HIGHEST, "horizon": "forever"}, "'forever' is not an option for horizon"),
    ],
)
def test_invalid_answers(answers: dict, message: str) -> None:
    with pytest.raises(InvalidAnswers, match=message):
        validate_answers(answers)


def test_dimension_score_rescales_average() -> None:
    # Capacity answers scoring 3, 4, 4, 4 -> average 3.75 -> 68.75 -> 68.8
    answers = {**LOWEST, "horizon": "3_5y", "emergency_fund": "3_6m",
               "income_stability": "stable", "emi_share": "10_25"}
    assert dimension_score(answers, "capacity") == 68.8


# --- API --------------------------------------------------------------------

def test_questions_are_public(client: TestClient) -> None:
    body = client.get("/api/v1/risk-profile/questions").json()
    assert body["version"] == "risk-v1"
    assert len(body["questions"]) == len(QUESTIONS)
    assert "score" not in body["questions"][0]["options"][0]
    assert [p["id"] for p in body["profiles"]] == ORDER


def test_profile_requires_login(client: TestClient) -> None:
    assert client.get("/api/v1/risk-profile").status_code == 401
    assert client.put("/api/v1/risk-profile", json={"answers": HIGHEST}).status_code == 401


def test_save_and_read_profile(client: TestClient, auth_headers: dict[str, str]) -> None:
    assert client.get("/api/v1/risk-profile", headers=auth_headers).status_code == 404

    saved = client.put("/api/v1/risk-profile", headers=auth_headers, json={"answers": HIGHEST})
    assert saved.status_code == 200
    assert saved.json()["profile"] == "aggressive"
    assert saved.json()["answers"] == HIGHEST

    # Saving again replaces the profile instead of adding a second one.
    lowered = {**HIGHEST, "horizon": "under_1y"}
    client.put("/api/v1/risk-profile", headers=auth_headers, json={"answers": lowered})
    read = client.get("/api/v1/risk-profile", headers=auth_headers).json()
    assert read["profile"] == "conservative"
    assert read["answers"] == lowered
    assert "user_id" not in read


def test_rejects_invalid_answers(client: TestClient, auth_headers: dict[str, str]) -> None:
    bad = client.put(
        "/api/v1/risk-profile", headers=auth_headers, json={"answers": {"horizon": "5_10y"}}
    )
    assert bad.status_code == 422
    assert "missing answers" in bad.text
