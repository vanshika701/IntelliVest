"""Combined financial health score (Phase 8): a fixed, explainable 0-100
number built from the budget analysis. Pure functions, no I/O. Weights and
scales are in budget_config.

A component that can't be measured (e.g. no emergency savings entered) is left
out and the others are re-weighted, with `complete` False.
"""

from app.core.budget_config import (
    BUCKET_TARGETS_PCT,
    EMERGENCY_FUND_MAX_MONTHS,
    HEALTH_BANDS,
    HEALTH_DEBT_FULL_PCT,
    HEALTH_DEBT_ZERO_PCT,
    HEALTH_OVERSPEND_ZERO_PCT,
    HEALTH_WEIGHTS,
)
from app.services.budget_rules import inr


def _clamp(x: float) -> float:
    return max(0.0, min(100.0, x))


def health_score(analysis: dict) -> dict:
    income = analysis["income"]
    if income <= 0:
        return {
            "score": None,
            "band": None,
            "complete": False,
            "components": [],
            "message": "Add your monthly income to see your score.",
        }

    target = BUCKET_TARGETS_PCT["savings"]
    savings = analysis["savings_rate_pct"]
    debt = next(c for c in analysis["categories"] if c["category"] == "emi_debt")["pct_of_income"]
    months = analysis["emergency_fund"]["months_covered"]
    overspend = analysis["total_overspend"] / income * 100

    parts: list[tuple[str, str, float | None, str]] = [
        (
            "savings",
            "Savings rate",
            _clamp(savings / target * 100),
            f"You keep {savings:g}% of income; the target is {target:g}%.",
        ),
        (
            "debt",
            "Debt load",
            _clamp((HEALTH_DEBT_ZERO_PCT - debt) / (HEALTH_DEBT_ZERO_PCT - HEALTH_DEBT_FULL_PCT) * 100),
            f"EMIs take {debt:g}% of income; up to {HEALTH_DEBT_FULL_PCT:g}% gets full marks.",
        ),
        (
            "emergency",
            "Emergency fund",
            None if months is None else _clamp(months / EMERGENCY_FUND_MAX_MONTHS * 100),
            "Add your emergency savings and essential spending to include this."
            if months is None
            else f"Covers {months:g} months of essentials; {EMERGENCY_FUND_MAX_MONTHS} gets full marks.",
        ),
        (
            "spending",
            "Spending within guidelines",
            _clamp((1 - overspend / HEALTH_OVERSPEND_ZERO_PCT) * 100),
            f"{inr(analysis['total_overspend'])}/month over the category guidelines.",
        ),
    ]
    measured = [(pid, value) for pid, _, value, _ in parts if value is not None]
    total_weight = sum(HEALTH_WEIGHTS[pid] for pid, _ in measured)
    score = round(sum(HEALTH_WEIGHTS[pid] * value for pid, value in measured) / total_weight)
    return {
        "score": score,
        "band": next(label for minimum, label in HEALTH_BANDS if score >= minimum),
        "complete": len(measured) == len(parts),
        "basis": analysis["basis"],
        "components": [
            {
                "id": pid,
                "name": name,
                "score": None if value is None else round(value),
                "weight": HEALTH_WEIGHTS[pid],
                "detail": detail,
            }
            for pid, name, value, detail in parts
        ],
        "message": None,
    }
