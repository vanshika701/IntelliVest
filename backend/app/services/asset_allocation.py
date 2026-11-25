"""Pure Phase 7 asset allocation: risk profile + goal horizon -> equity /
debt / gold percentages, with the reasons. Rules live in
core/allocation_config.py.

This is the first of the two layers in the plan: most of a portfolio's
ups and downs come from this split, not from which stocks fill the
equity part (step 4).
"""

from app.core.allocation_config import (
    ALLOCATION_VERSION,
    BASE_SPLITS,
    HORIZON_LIMITS,
    LONG_HORIZON_DEBT_STYLE,
    SOURCED_PROFILES,
    HorizonLimit,
)


def horizon_limit(horizon_months: int) -> HorizonLimit | None:
    return next((h for h in HORIZON_LIMITS if horizon_months <= h.max_months), None)


def allocate(profile_id: str, horizon_months: int) -> dict:
    """Split for one goal. Raises KeyError for an unknown profile and
    ValueError for a horizon under one month."""
    if horizon_months < 1:
        raise ValueError("horizon_months must be at least 1")
    base = BASE_SPLITS[profile_id]
    equity, gold = base.equity, base.gold

    adjustments = []
    limit = horizon_limit(horizon_months)
    if limit is not None:
        if equity > limit.max_equity:
            adjustments.append(
                {"asset": "equity", "from_pct": equity, "to_pct": limit.max_equity,
                 "reason": limit.reason}
            )
            equity = limit.max_equity
        if gold > limit.max_gold:
            adjustments.append(
                {"asset": "gold", "from_pct": gold, "to_pct": limit.max_gold,
                 "reason": limit.reason}
            )
            gold = limit.max_gold

    return {
        "profile": profile_id,
        "horizon_months": horizon_months,
        "equity_pct": equity,
        "debt_pct": 100 - equity - gold,  # whatever was cut moves to debt
        "gold_pct": gold,
        "debt_style": limit.debt_style if limit else LONG_HORIZON_DEBT_STYLE,
        "base": {"equity_pct": base.equity, "debt_pct": base.debt, "gold_pct": base.gold},
        "base_is_sourced": profile_id in SOURCED_PROFILES,
        "adjustments": adjustments,
        "version": ALLOCATION_VERSION,
    }
