"""Phase 8 smart budgeter: glue between storage and the pure engines
(`budget_rules`, `goal_planner`). All numbers come from those engines."""

from datetime import UTC, datetime

from app.core.budget_config import (
    ACTUAL_WINDOW_MONTHS,
    BUCKET_TARGETS_PCT,
    CATEGORIES,
    CATEGORY_BY_ID,
    DEBT_TO_INCOME_CRITICAL_PCT,
    DEFAULT_STEP_UP_PCT,
    DISCLAIMER,
    EMERGENCY_FUND_MAX_MONTHS,
    EMERGENCY_FUND_MIN_MONTHS,
    RETURN_ASSUMPTIONS,
)
from app.data import budget_repository as repo
from app.services import budget_explainer
from app.services.budget_rules import analyze_budget, improve_focus, inr
from app.services.goal_planner import plan_goal


def categories_meta() -> dict:
    return {
        "categories": [
            {
                "id": c.id,
                "name": c.name,
                "bucket": c.bucket,
                "min_pct": c.min_pct,
                "max_pct": c.max_pct,
                "note": c.note,
            }
            for c in CATEGORIES
        ],
        "bucket_targets_pct": BUCKET_TARGETS_PCT,
        "debt_to_income_critical_pct": DEBT_TO_INCOME_CRITICAL_PCT,
        "emergency_fund_months": [EMERGENCY_FUND_MIN_MONTHS, EMERGENCY_FUND_MAX_MONTHS],
        "return_assumptions": [
            {"max_months": r.max_months, "annual_return_pct": r.annual_return_pct, "label": r.label}
            for r in RETURN_ASSUMPTIONS
        ],
        "default_step_up_pct": DEFAULT_STEP_UP_PCT,
        "actual_window_months": ACTUAL_WINDOW_MONTHS,
        "llm_explanations": budget_explainer.llm_enabled(),
        "disclaimer": DISCLAIMER,
    }


# --- Profile ----------------------------------------------------------------

async def get_profile(user_id: str) -> dict | None:
    return await repo.get_profile(user_id)


async def save_profile(user_id: str, data: dict) -> dict:
    # Drop zero estimates so the stored doc stays small; missing == 0.
    data["estimates"] = {k: float(v) for k, v in data.get("estimates", {}).items() if v}
    data["updated_at"] = datetime.now(UTC)
    return await repo.upsert_profile(user_id, data)


def profile_warnings(profile: dict) -> list[str]:
    income = profile.get("monthly_income", 0) or 0
    total = sum(profile.get("estimates", {}).values())
    if income <= 0:
        return ["Monthly income is 0, so benchmarks and goal affordability can't be checked."]
    if total > income:
        return [f"Your estimates total {inr(total)}, which is {inr(total - income)} more than your income of {inr(income)}."]
    return []


# --- Actual spending ----------------------------------------------------------

def _window_start(now: datetime, months: int) -> datetime:
    """First day of the calendar month `months - 1` months before `now`."""
    year, month = now.year, now.month - (months - 1)
    while month <= 0:
        month += 12
        year -= 1
    return datetime(year, month, 1, tzinfo=UTC)


async def actual_monthly_spend(user_id: str, now: datetime | None = None) -> dict:
    """Average monthly spend per category over the last ACTUAL_WINDOW_MONTHS
    calendar months (including the current one), dividing by the number of
    months that actually have expenses so a new user isn't averaged down."""
    now = now or datetime.now(UTC)
    since = _window_start(now, ACTUAL_WINDOW_MONTHS)
    rows = await repo.spend_by_category_and_month(user_id, since)
    months = sorted({r["month"] for r in rows})
    by_category: dict[str, float] = {}
    for r in rows:
        cat = r["category"] if r["category"] in CATEGORY_BY_ID else "other"
        by_category[cat] = by_category.get(cat, 0.0) + r["total"]
    n = max(len(months), 1)
    return {
        "has_data": bool(rows),
        "months": months,
        "window_start": since,
        "by_category": {k: round(v / n, 2) for k, v in by_category.items()},
    }


# --- Analysis -----------------------------------------------------------------

async def _inputs(user_id: str, basis: str) -> tuple[dict | None, dict, str]:
    profile = await repo.get_profile(user_id)
    actual = await actual_monthly_spend(user_id)
    if basis == "auto":
        basis = "actual" if actual["has_data"] else "estimated"
    return profile, actual, basis


def _analysis(profile: dict | None, actual: dict, basis: str) -> dict:
    estimates = (profile or {}).get("estimates", {})
    spend = actual["by_category"] if basis == "actual" else estimates
    return analyze_budget(
        income=float((profile or {}).get("monthly_income", 0) or 0),
        spend=spend,
        estimates=estimates if profile else None,
        emergency_fund=(profile or {}).get("emergency_fund"),
        basis=basis,
    )


async def overview(user_id: str) -> dict:
    """Everything the budget screen needs: profile, estimated vs actual per
    category, and the analysis on the default basis."""
    profile, actual, basis = await _inputs(user_id, "auto")
    estimates = (profile or {}).get("estimates", {})
    comparison = []
    for c in CATEGORIES:
        est = float(estimates.get(c.id, 0) or 0)
        act = actual["by_category"].get(c.id) if actual["has_data"] else None
        comparison.append(
            {
                "category": c.id,
                "name": c.name,
                "bucket": c.bucket,
                "estimated": est,
                "actual": act,
                "difference": None if act is None else round(act - est, 2),
            }
        )
    return {
        "has_profile": profile is not None,
        "profile": profile,
        "profile_warnings": profile_warnings(profile) if profile else [],
        "actual": {
            "has_data": actual["has_data"],
            "months": actual["months"],
            "window_start": actual["window_start"],
        },
        "comparison": comparison,
        "analysis": _analysis(profile, actual, basis) if profile else None,
    }


async def analysis(user_id: str, basis: str = "auto") -> dict | None:
    profile, actual, basis = await _inputs(user_id, basis)
    if profile is None:
        return None
    return _analysis(profile, actual, basis)


async def improve(user_id: str, focus: str, basis: str = "auto") -> dict | None:
    result = await analysis(user_id, basis)
    if result is None:
        return None
    return {**improve_focus(result, focus), "basis": result["basis"], "disclaimer": DISCLAIMER}


# --- Goals --------------------------------------------------------------------

async def _surplus_and_overspent(user_id: str) -> tuple[float | None, list[dict]]:
    result = await analysis(user_id, "auto")
    if result is None:
        return None, []
    by_id = {c["category"]: c for c in result["categories"]}
    return result["surplus"], [by_id[i] for i in result["overspent"]]


def _plan(goal: dict, surplus, overspent) -> dict:
    return plan_goal(
        name=goal["name"],
        target=goal["target_amount"],
        months=goal["horizon_months"],
        annual_return_pct=goal.get("annual_return_pct"),
        step_up_pct=goal.get("step_up_pct"),
        monthly_surplus=surplus,
        overspent=overspent,
    )


async def preview_goal(user_id: str, goal: dict) -> dict:
    surplus, overspent = await _surplus_and_overspent(user_id)
    return _plan(goal, surplus, overspent)


async def create_goal(user_id: str, goal: dict) -> dict:
    doc = {**goal, "user_id": user_id, "created_at": datetime.now(UTC)}
    stored = await repo.insert_goal(doc)
    surplus, overspent = await _surplus_and_overspent(user_id)
    return {**stored, "plan": _plan(stored, surplus, overspent)}


async def list_goals(user_id: str) -> dict:
    goals = await repo.list_goals(user_id)
    surplus, overspent = await _surplus_and_overspent(user_id)
    items = [{**g, "plan": _plan(g, surplus, overspent)} for g in goals]
    total_flat = round(sum(i["plan"]["flat"]["monthly"] for i in items), 2)
    combined = None
    if surplus is not None and items:
        combined = {
            "total_flat_monthly": total_flat,
            "monthly_surplus": surplus,
            "fits": surplus >= total_flat,
            "message": (
                f"All goals together need {inr(total_flat)}/month as flat SIPs, "
                + ("which fits your surplus." if surplus >= total_flat else f"more than your surplus of {inr(surplus)}.")
            ),
        }
    return {"items": items, "combined": combined, "disclaimer": DISCLAIMER}


async def delete_goal(user_id: str, goal_id: str) -> bool:
    return await repo.delete_goal(user_id, goal_id)


# --- Optional natural-language explanation -------------------------------------

async def explain(user_id: str, kind: str, focus: str | None, goal_id: str | None, basis: str) -> dict | None:
    """Recompute server-side (never trust client numbers), then hand the
    engine's own sentences to the explainer."""
    if kind == "improve":
        result = await improve(user_id, focus or "all", basis)
        if result is None:
            return None
        facts = [result["summary"]]
        facts += [o["message"] for o in result["other_overspends"]]
        facts.append(result["emergency_fund"]["message"])
    else:
        goal = await repo.get_goal(user_id, goal_id or "")
        if goal is None:
            return None
        surplus, overspent = await _surplus_and_overspent(user_id)
        plan = _plan(goal, surplus, overspent)
        a = plan["assumption"]
        facts = [
            plan["summary"],
            f"This assumes {a['annual_return_pct']:g}% a year ({a['label']}).",
            plan["affordability"]["message"],
            *[o["message"] for o in plan["affordability"]["options"]],
            *plan["notes"],
        ]
    return await budget_explainer.explain(facts)
