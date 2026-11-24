"""Goal-based SIP planner (Phase 8). Deterministic maths only.

Convention (same as the instrument return calculator, frontend
`lib/returns.ts`): one contribution at the START of each month, monthly
rate i = annual / 12, so the flat-SIP future value is the annuity-due
formula FV = P × [((1 + i)^n − 1) / i] × (1 + i).

Step-up SIP: the monthly amount is constant within each 12-month year and
rises by s% at the start of every following year. Its future value is the
sum over months m = 0..n−1 of P × (1 + s)^⌊m/12⌋ × (1 + i)^(n − m), which
is linear in P, so the starting amount is FV / that factor (exact for
partial final years, no approximation).
"""

from app.core.budget_config import (
    DEFAULT_STEP_UP_PCT,
    DISCLAIMER,
    MAX_EXTENSION_SEARCH_MONTHS,
    SAFER_INSTRUMENTS_NOTE,
    SHORT_HORIZON_MONTHS,
    default_return_for,
)
from app.services.budget_rules import inr


def _monthly_rate(annual_pct: float) -> float:
    return annual_pct / 100 / 12


def flat_factor(months: int, annual_pct: float) -> float:
    """FV of ₹1/month for `months` months (annuity due)."""
    if months <= 0:
        return 0.0
    i = _monthly_rate(annual_pct)
    if i == 0:
        return float(months)
    return ((1 + i) ** months - 1) / i * (1 + i)


def step_up_factor(months: int, annual_pct: float, step_up_pct: float) -> float:
    """FV of a step-up SIP that starts at ₹1/month."""
    i = _monthly_rate(annual_pct)
    g = 1 + step_up_pct / 100
    return sum(g ** (m // 12) * (1 + i) ** (months - m) for m in range(months))


def required_flat_sip(target: float, months: int, annual_pct: float) -> float:
    factor = flat_factor(months, annual_pct)
    return target / factor if factor > 0 else float("inf")


def required_step_up_start(target: float, months: int, annual_pct: float, step_up_pct: float) -> float:
    factor = step_up_factor(months, annual_pct, step_up_pct)
    return target / factor if factor > 0 else float("inf")


def step_up_schedule(start: float, months: int, step_up_pct: float) -> list[dict]:
    """Monthly amount per year of the plan, e.g. [{year: 1, monthly: 10000, months: 12}, ...]."""
    g = 1 + step_up_pct / 100
    rows = []
    for year in range((months + 11) // 12):
        n_months = min(12, months - year * 12)
        rows.append({"year": year + 1, "monthly": round(start * g**year, 2), "months": n_months})
    return rows


def _horizon_text(months: int) -> str:
    if months % 12 == 0:
        years = months // 12
        return f"{years} year{'s' if years != 1 else ''}"
    if months < 12:
        return f"{months} month{'s' if months != 1 else ''}"
    return f"{months // 12}y {months % 12}m"


def plan_goal(
    name: str,
    target: float,
    months: int,
    annual_return_pct: float | None = None,
    step_up_pct: float | None = None,
    monthly_surplus: float | None = None,
    overspent: list[dict] | None = None,
) -> dict:
    """Plan A (flat) vs Plan B (step-up), affordability and options.

    `overspent` is the rules engine's over-benchmark categories (each with
    `name` and `overspend_amount`), used to suggest where money can come
    from. `monthly_surplus` None means "unknown" (no budget set up).
    """
    assumption = default_return_for(months)
    rate_is_default = annual_return_pct is None
    rate = assumption.annual_return_pct if rate_is_default else annual_return_pct
    step = DEFAULT_STEP_UP_PCT if step_up_pct is None else step_up_pct

    flat = required_flat_sip(target, months, rate)
    step_start = required_step_up_start(target, months, rate, step)
    flat_invested = flat * months
    schedule = step_up_schedule(step_start, months, step)
    step_invested = sum(r["monthly"] * r["months"] for r in schedule)

    notes: list[str] = []
    if months <= SHORT_HORIZON_MONTHS:
        notes.append(SAFER_INSTRUMENTS_NOTE)
    if months <= 12:
        notes.append(
            "With a horizon of a year or less there's no annual step-up, so both plans are the "
            "same; a savings account, RD or liquid fund is usually simpler than a SIP."
        )

    horizon = _horizon_text(months)
    summary = (
        f"To reach {inr(target)} in {horizon} you can start a {inr(flat)}/month SIP now"
        + (
            f", or start with {inr(step_start)} and step up {step:g}% each year."
            if months > 12 and step > 0
            else "."
        )
    )

    affordability = _affordability(
        target, months, rate, rate_is_default, flat, monthly_surplus, overspent or []
    )

    return {
        "name": name,
        "target_amount": round(target, 2),
        "horizon_months": months,
        "horizon_text": horizon,
        "assumption": {
            "annual_return_pct": rate,
            "is_default": rate_is_default,
            "label": assumption.label if rate_is_default else "Your chosen expected return",
            "step_up_pct": step,
            "contribution_timing": "start of each month",
        },
        "flat": {
            "monthly": round(flat, 2),
            "total_invested": round(flat_invested, 2),
            "estimated_gains": round(target - flat_invested, 2),
        },
        "step_up": {
            "start_monthly": round(step_start, 2),
            "final_monthly": schedule[-1]["monthly"] if schedule else 0,
            "schedule": schedule,
            "total_invested": round(step_invested, 2),
            "estimated_gains": round(target - step_invested, 2),
        },
        "affordability": affordability,
        "summary": summary,
        "notes": notes,
        "disclaimer": DISCLAIMER,
    }


def _affordability(target, months, rate, rate_is_default, flat, surplus, overspent) -> dict:
    if surplus is None:
        return {
            "status": "unknown",
            "monthly_surplus": None,
            "message": "Set up your budget (income and spending) to check whether this SIP fits.",
            "options": [],
        }

    surplus = round(surplus, 2)
    if surplus >= flat:
        return {
            "status": "affordable",
            "monthly_surplus": surplus,
            "message": f"The {inr(flat)}/month SIP fits within your monthly surplus of {inr(surplus)}.",
            "options": [],
        }

    gap = flat - max(surplus, 0)
    options: list[dict] = []

    if surplus > 0:
        # Option 1: extend the timeline until the flat SIP fits.
        for m in range(months + 1, MAX_EXTENSION_SEARCH_MONTHS + 1):
            r = default_return_for(m).annual_return_pct if rate_is_default else rate
            if required_flat_sip(target, m, r) <= surplus:
                options.append(
                    {
                        "type": "extend_timeline",
                        "horizon_months": m,
                        "monthly": round(required_flat_sip(target, m, r), 2),
                        "message": f"Extend the timeline to {_horizon_text(m)}: about "
                        f"{inr(required_flat_sip(target, m, r))}/month at {r:g}% a year.",
                    }
                )
                break
        # Option 2: reduce the target to what the surplus reaches.
        reachable = surplus * flat_factor(months, rate)
        options.append(
            {
                "type": "reduce_target",
                "target_amount": round(reachable, 2),
                "message": f"Reduce the target to about {inr(reachable)}: that's what "
                f"{inr(surplus)}/month reaches in {_horizon_text(months)}.",
            }
        )

    # Option 3: free up money from over-benchmark categories.
    freed, picks = 0.0, []
    for cat in overspent:
        if freed >= gap:
            break
        cut = min(cat["overspend_amount"], gap - freed)
        if cut <= 0:
            continue
        picks.append({"category": cat["category"], "name": cat["name"], "amount": round(cut, 2)})
        freed += cut
    if picks:
        parts = ", ".join(f"{inr(p['amount'])} from {p['name']}" for p in picks)
        covered = "covers the gap" if freed >= gap - 0.5 else f"covers {inr(freed)} of the {inr(gap)} gap"
        options.append(
            {
                "type": "free_up",
                "cuts": picks,
                "total": round(freed, 2),
                "message": f"Cut back to the benchmark: {parts}. That {covered}.",
            }
        )

    if surplus <= 0:
        msg = (
            f"You have no monthly surplus right now (income minus spending is {inr(surplus)}), "
            f"so a {inr(flat)}/month SIP doesn't fit yet."
        )
    else:
        msg = (
            f"The {inr(flat)}/month SIP is {inr(gap)} more than your monthly surplus of "
            f"{inr(surplus)}."
        )
    return {"status": "not_affordable", "monthly_surplus": surplus, "gap": round(gap, 2), "message": msg, "options": options}
