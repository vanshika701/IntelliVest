"""Deterministic overspend rules (Phase 8). Pure functions: given income,
monthly spend per category and the user's own estimates, return flags and
₹ figures. No I/O, no ML, no LLM. Every threshold comes from
`app/core/budget_config.py`.
"""

from decimal import ROUND_HALF_UP, Decimal

from app.core.budget_config import (
    BUCKET_TARGETS_PCT,
    CATEGORIES,
    CATEGORY_BY_ID,
    DEBT_TO_INCOME_CRITICAL_PCT,
    EMERGENCY_FUND_MAX_MONTHS,
    EMERGENCY_FUND_MIN_MONTHS,
    TOP_OTHER_OVERSPENDS,
)


def _r(x: float) -> float:
    return round(x, 2)


def inr(amount: float) -> str:
    """₹ with Indian digit grouping, no decimals: ₹1,23,456.

    Rounds the 2-decimal value half-up (not Python's banker's rounding),
    matching how the UI formats the same API numbers, so a sentence and the
    figure next to it never differ by ₹1."""
    two_dp = Decimal(str(abs(amount))).quantize(Decimal("0.01"), ROUND_HALF_UP)
    s = str(int(two_dp.quantize(Decimal(1), ROUND_HALF_UP)))
    if len(s) > 3:
        head, tail = s[:-3], s[-3:]
        groups = []
        while len(head) > 2:
            groups.insert(0, head[-2:])
            head = head[:-2]
        if head:
            groups.insert(0, head)
        s = ",".join(groups) + "," + tail
    return f"{'-' if amount < 0 else ''}₹{s}"


def _pct(amount: float, income: float) -> float | None:
    return _r(amount / income * 100) if income > 0 else None


def _range_text(lo: float | None, hi: float | None) -> str:
    if lo is not None and hi is not None:
        return f"{lo:g}-{hi:g}%"
    if lo is not None:
        return f"at least {lo:g}%"
    if hi is not None:
        return f"at most {hi:g}%"
    return "no fixed benchmark"


def assess_category(cat_id: str, amount: float, income: float, estimate: float | None) -> dict:
    """Assess one category against its benchmark and the user's estimate."""
    cat = CATEGORY_BY_ID[cat_id]
    pct = _pct(amount, income)
    is_savings = cat.bucket == "savings"

    status = "no_benchmark"
    over_by = 0.0
    target: float | None = None
    if income <= 0:
        status = "no_income"
    elif is_savings:
        # For savings, below the minimum is the problem.
        if cat.min_pct is not None:
            minimum = cat.min_pct / 100 * income
            status = "below_target" if amount < minimum else "within"
            target = max(amount, minimum)
    elif cat.max_pct is not None:
        cap = cat.max_pct / 100 * income
        if amount > cap:
            status = "over"
            over_by = amount - cap
            target = cap
        elif cat.min_pct is not None and amount < cat.min_pct / 100 * income:
            status = "under"
        else:
            status = "within"
        if cat_id == "emi_debt" and pct is not None and pct > DEBT_TO_INCOME_CRITICAL_PCT:
            status = "critical"

    vs_estimate = None if estimate is None else _r(amount - estimate)

    return {
        "category": cat_id,
        "name": cat.name,
        "bucket": cat.bucket,
        "amount": _r(amount),
        "pct_of_income": pct,
        "benchmark_min_pct": cat.min_pct,
        "benchmark_max_pct": cat.max_pct,
        "benchmark_text": _range_text(cat.min_pct, cat.max_pct),
        "status": status,
        "overspend_amount": _r(over_by),
        "suggested_target": None if target is None else _r(target),
        "estimate": None if estimate is None else _r(estimate),
        "vs_estimate": vs_estimate,
        "message": category_message(cat.name, amount, pct, status, over_by, target, cat),
    }


def category_message(name, amount, pct, status, over_by, target, cat) -> str:
    """Template sentence for one category. The fallback when no LLM is used."""
    bench = _range_text(cat.min_pct, cat.max_pct)
    if status == "no_income":
        return f"You're spending {inr(amount)}/month on {name}. Add your monthly income to compare it with a benchmark."
    if pct is None or status == "no_benchmark":
        return f"You're spending {inr(amount)}/month on {name}. There's no fixed benchmark for this category."
    head = f"You're spending {pct:g}% of income on {name} ({inr(amount)}/month); the recommended range is {bench}."
    if status in ("over", "critical"):
        msg = f"{head} You're overspending by {inr(over_by)}/month. Suggested target: {inr(target)}."
        if status == "critical":
            msg += (
                f" Total EMIs above {DEBT_TO_INCOME_CRITICAL_PCT:g}% of take-home pay are a "
                "warning sign; avoid new loans and consider prepaying the costliest one."
            )
        return msg
    if status == "below_target":
        return f"{head} Try to raise it to {inr(target)}/month."
    return f"{head} You're within the guideline."


def analyze_budget(
    income: float,
    spend: dict[str, float],
    estimates: dict[str, float] | None = None,
    emergency_fund: float | None = None,
    basis: str = "estimated",
) -> dict:
    """Full rule-based analysis.

    `spend` is monthly ₹ per category id (missing = 0). `estimates` is the
    user's own monthly estimate per category (used for vs-estimate). Savings
    rate follows 50/30/20: (income - needs - wants) / income, so unspent
    income counts as saved.
    """
    estimates = estimates or {}
    categories = [
        assess_category(c.id, float(spend.get(c.id, 0) or 0), income, estimates.get(c.id))
        for c in CATEGORIES
    ]

    totals = {"needs": 0.0, "wants": 0.0, "savings": 0.0}
    for row in categories:
        totals[row["bucket"]] += row["amount"]
    total_spend = totals["needs"] + totals["wants"]
    surplus = income - total_spend
    savings_amount = max(surplus, 0.0)

    buckets = []
    for bucket, target_pct in BUCKET_TARGETS_PCT.items():
        amount = savings_amount if bucket == "savings" else totals[bucket]
        target_amount = target_pct / 100 * income
        if income <= 0:
            status = "no_income"
        elif bucket == "savings":
            status = "below_target" if amount < target_amount else "within"
        else:
            status = "over" if amount > target_amount else "within"
        buckets.append(
            {
                "bucket": bucket,
                "amount": _r(amount),
                "pct_of_income": _pct(amount, income),
                "target_pct": target_pct,
                "target_amount": _r(target_amount),
                "difference": _r(amount - target_amount),
                "status": status,
            }
        )

    # Emergency fund: target months x essential (needs) spending.
    essentials = totals["needs"]
    ef_min = EMERGENCY_FUND_MIN_MONTHS * essentials
    ef_max = EMERGENCY_FUND_MAX_MONTHS * essentials
    if emergency_fund is None:
        ef_status, months_covered = "unknown", None
    else:
        months_covered = _r(emergency_fund / essentials) if essentials > 0 else None
        if essentials <= 0:
            ef_status = "unknown"
        elif emergency_fund <= 0:
            ef_status = "missing"
        elif emergency_fund < ef_min:
            ef_status = "partial"
        else:
            ef_status = "adequate"
    emergency = {
        "current": None if emergency_fund is None else _r(emergency_fund),
        "monthly_essentials": _r(essentials),
        "target_min": _r(ef_min),
        "target_max": _r(ef_max),
        "months_covered": months_covered,
        "status": ef_status,
        "shortfall": _r(max(ef_min - (emergency_fund or 0), 0.0)),
        "message": _emergency_message(ef_status, emergency_fund, ef_min, ef_max, months_covered),
    }

    overspent = sorted(
        (c for c in categories if c["status"] in ("over", "critical")),
        key=lambda c: c["overspend_amount"],
        reverse=True,
    )

    return {
        "basis": basis,
        "income": _r(income),
        "total_spend": _r(total_spend),
        "surplus": _r(surplus),
        "savings_rate_pct": _pct(savings_amount, income),
        "categories": categories,
        "buckets": buckets,
        "emergency_fund": emergency,
        "overspent": [c["category"] for c in overspent],
        "total_overspend": _r(sum(c["overspend_amount"] for c in overspent)),
        "total_allocated": _r(total_spend + totals["savings"]),
        "warnings": _warnings(income, total_spend, surplus, total_spend + totals["savings"]),
    }


def _emergency_message(status, current, lo, hi, months) -> str:
    rng = f"{inr(lo)}-{inr(hi)} ({EMERGENCY_FUND_MIN_MONTHS}-{EMERGENCY_FUND_MAX_MONTHS} months of essentials)"
    if status == "unknown":
        return f"Add your current emergency savings to check them against the {EMERGENCY_FUND_MIN_MONTHS}-{EMERGENCY_FUND_MAX_MONTHS} month target."
    if status == "missing":
        return f"You don't have an emergency fund yet. Aim for {rng} before investing for goals."
    if status == "partial":
        return f"Your emergency fund of {inr(current)} covers {months:g} months. Build it up to {rng}."
    return f"Your emergency fund of {inr(current)} covers {months:g} months of essentials. That's within or above the target."


def _warnings(income: float, total_spend: float, surplus: float, allocated: float) -> list[str]:
    if income <= 0:
        return ["Monthly income is zero or not set, so percentages and benchmarks can't be computed."]
    if surplus < 0:
        return [f"Spending exceeds income by {inr(-surplus)}/month."]
    if allocated > income:
        over = inr(allocated - income)
        return [
            f"Spending plus planned savings ({inr(allocated)}) is more than your income "
            + f"({inr(income)}) by {over}/month."
        ]
    return []


def improve_focus(analysis: dict, focus: str) -> dict:
    """The 'improve my budgeting' answer for one category (or 'all')."""
    by_id = {c["category"]: c for c in analysis["categories"]}
    others_pool = [by_id[i] for i in analysis["overspent"] if i != focus]
    others = others_pool[:TOP_OTHER_OVERSPENDS]

    if focus == "all":
        focus_row = None
        lines = []
        for b in analysis["buckets"]:
            if b["status"] == "over":
                lines.append(
                    f"{b['bucket'].title()} take {b['pct_of_income']:g}% of income vs the {b['target_pct']:g}% "
                    f"guideline: {inr(b['difference'])}/month over."
                )
            elif b["status"] == "below_target":
                lines.append(
                    f"Savings are {b['pct_of_income']:g}% of income vs the {b['target_pct']:g}% target: "
                    f"{inr(-b['difference'])}/month short."
                )
        if not lines and analysis["income"] > 0:
            lines.append("Your budget fits the 50/30/20 guideline.")
        summary = " ".join(lines + analysis["warnings"])
    else:
        focus_row = by_id[focus]
        summary = focus_row["message"]
        if focus_row["vs_estimate"] and analysis["basis"] == "actual" and focus_row["estimate"] is not None:
            diff = focus_row["vs_estimate"]
            word = "more" if diff > 0 else "less"
            summary += f" That's {inr(abs(diff))} {word} than your own estimate of {inr(focus_row['estimate'])}."

    return {
        "focus": focus,
        "focus_category": focus_row,
        "summary": summary,
        "other_overspends": others,
        "emergency_fund": analysis["emergency_fund"],
    }
