"""Phase 9 rules engine: module results (modules.py) in, prioritised actions
out. Pure functions, no I/O, no ML, no LLM. Every number in an action comes
from a module's data; every action names the modules it used.

    Action = {
        "id": "emergency_fund",            # rule id, also its PRIORITY key
        "priority": 20,                    # lower is shown first
        "severity": "high" | "medium" | "low",
        "title": str, "detail": str,       # template sentences
        "facts": [str],                    # the module facts it rests on
        "contributors": [module ids],
        "link": "/budget" | ...,           # where the user can act on it
        "data": {...},                     # figures, e.g. amounts to move
    }

Setup steps ("answer the risk questionnaire") are returned separately:
they unlock advice rather than being advice.
"""

from app.core.advisor_config import (
    CONCENTRATION_PCT,
    MAX_UNCLASSIFIED_PCT_FOR_DRIFT,
    PRIORITY,
    REBALANCE_THRESHOLD_PP,
    REVIEW_SECTOR_FALL_PCT,
)
from app.core.constants import TICKER_TO_SECTOR
from app.services.advisor.modules import is_usable
from app.services.budget_rules import inr

CLASSES = ("equity", "debt", "gold")
CLASS_LABEL = {"equity": "stocks", "debt": "debt", "gold": "gold"}


def action(rule: str, severity: str, title: str, detail: str, contributors: list[dict],
           link: str, data: dict | None = None, about: list[str] | None = None) -> dict:
    """`about` narrows each contributor's facts to those mentioning one of
    these names (e.g. one stock and its sector); by default all are kept."""
    facts = [f for m in contributors for f in m["facts"]]
    if about:
        facts = [f for f in facts if any(name in f for name in about)]
    return {
        "id": rule, "priority": PRIORITY[rule], "severity": severity, "title": title, "detail": detail,
        "facts": facts,
        "contributors": [m["module"] for m in contributors],
        "link": link, "data": data or {},
    }


# --- Safety net and debt (budget) --------------------------------------------------

def budget_actions(budget: dict) -> list[dict]:
    if not is_usable(budget):
        return []
    d = budget["data"]
    actions = []
    if d["surplus"] < 0:
        top = sorted(d["overspent"], key=lambda c: c["overspend_amount"], reverse=True)[:3]
        where = ", ".join(f"{c['name']} ({inr(c['overspend_amount'])} over)" for c in top)
        actions.append(action(
            "spending_exceeds_income", "high",
            f"You spend {inr(-d['surplus'])} a month more than you earn",
            "Fix this before saving or investing." + (f" Biggest overspends: {where}." if where else ""),
            [budget], "/budget", {"monthly_gap": -d["surplus"]},
        ))

    ef = d["emergency_fund"]
    if ef["status"] in ("missing", "partial") and ef["shortfall"] > 0:
        months = round(ef["shortfall"] / d["surplus"], 1) if d["surplus"] > 0 else None
        actions.append(action(
            "emergency_fund", "high",
            f"Build your emergency fund: {inr(ef['shortfall'])} to go",
            f"Aim for at least {inr(ef['target_min'])} (3 months of essentials) in a savings account "
            "or liquid fund before investing in stocks."
            + (f" At your current surplus that takes about {months:g} months." if months else ""),
            [budget], "/budget", {"shortfall": ef["shortfall"], "months_to_fill": months},
        ))

    emi = d["emi"]
    if emi["status"] in ("critical", "over"):
        critical = emi["status"] == "critical"
        actions.append(action(
            "debt_critical" if critical else "debt_high", "high" if critical else "medium",
            f"Loan EMIs take {emi['pct_of_income']:g}% of your income",
            ("Above 36% is a warning sign: avoid new loans and consider prepaying the costliest one."
             if critical else "Keep EMIs under 30% of income; avoid adding new loans for now."),
            [budget], "/budget", {"emi_pct": emi["pct_of_income"], "emi_amount": emi["amount"]},
        ))
    return actions


# --- Goals ---------------------------------------------------------------------------

def goal_actions(goals: dict) -> list[dict]:
    if not is_usable(goals):
        return []
    actions = []
    for g in goals["data"]["goals"]:
        if g["affordability"] != "not_affordable":
            continue
        actions.append(action(
            "goal_unaffordable", "medium",
            f'"{g["name"]}" needs {inr(g["flat_monthly"])} a month, more than you have spare',
            g["first_option"] or "Lower the target, extend the timeline or free up spending.",
            [goals], "/budget", {"goal_id": g["id"], "gap": g["gap"]},
        ))
    return actions


# --- Investing per the plan ---------------------------------------------------------------

def _equity_range(plan: dict, predictions: dict) -> tuple[float, float] | None:
    """Weighted average of the planned stocks' 1-year low and high cases.

    Averaging percentiles ignores diversification, so the true range of the
    stock part is narrower than this: it's a cautious, wide bound."""
    if not is_usable(predictions):
        return None
    ranges = {s["ticker"]: s for s in predictions["data"]["stocks"]}
    stocks = [h for h in plan["data"]["holdings"] if h["asset_class"] == "equity"]
    covered = [(h, ranges.get(h["instrument_id"].removeprefix("stock-"))) for h in stocks]
    covered = [(h, r) for h, r in covered if r]
    weight = sum(h["weight"] for h, _ in covered)
    total = sum(h["weight"] for h in stocks)
    if not covered or weight < 0.8 * total:  # too few stocks have ranges to say anything
        return None
    low = sum(h["weight"] * r["low_pct"] for h, r in covered) / weight
    high = sum(h["weight"] * r["high_pct"] for h, r in covered) / weight
    return round(low, 1), round(high, 1)


def invest_action(
    risk: dict, plan: dict, predictions: dict, blocked_by_safety: bool, safety_checked: bool
) -> list[dict]:
    if not (is_usable(risk) and is_usable(plan)):
        return []
    inputs, split = plan["data"]["inputs"], plan["data"]["split"]
    amounts = []
    if inputs.get("lump_sum"):
        amounts.append(f"{inr(inputs['lump_sum'])} now")
    if inputs.get("monthly_sip"):
        amounts.append(f"{inr(inputs['monthly_sip'])} a month")
    goal = inputs.get("goal")
    title = f"Invest {' and '.join(amounts) or 'as planned'}" + (f' for "{goal["name"]}"' if goal else "")
    detail = (f"Your plan: {split['equity']}% stocks, {split['debt']}% debt, {split['gold']}% gold, "
              f"matching your {risk['data']['label']} profile.")
    contributors = [risk, plan]
    rng = _equity_range(plan, predictions)
    if split["equity"] and rng:
        detail += (f" Over a year the stock part could plausibly end anywhere from about {rng[0]:+.0f}% "
                   f"to {rng[1]:+.0f}% (a cautious, wide range).")
        contributors.append(predictions)
    if plan["status"] == "stale":
        detail += " The plan is over a month old; rebuild it so it uses current prices."
    if blocked_by_safety:
        detail += " Do this once the steps above are in place."
    elif not safety_checked:
        detail += (" Your budget isn't set up, so we couldn't check your emergency fund or debts first;"
                   " set it up before investing.")
    return [action("invest_per_plan", "low" if blocked_by_safety else "medium", title, detail,
                   contributors, "/portfolio-plan", {"split": split, "equity_range_1y": rng})]


# --- Fine-tuning: rebalance, concentration, single holdings -------------------------------

def rebalance_action(holdings: dict, plan: dict) -> list[dict]:
    if not (is_usable(holdings) and is_usable(plan)):
        return []
    split = holdings["data"]["split_pct"]
    if split.get("unclassified", 0) > MAX_UNCLASSIFIED_PCT_FOR_DRIFT:
        return []
    classified = sum(split.get(c, 0) for c in CLASSES)
    if classified <= 0:
        return []
    current = {c: split.get(c, 0) / classified * 100 for c in CLASSES}  # % of classified value
    target = plan["data"]["split"]
    drift = {c: round(current[c] - target[c], 1) for c in CLASSES}
    worst = max(CLASSES, key=lambda c: abs(drift[c]))
    if abs(drift[worst]) < REBALANCE_THRESHOLD_PP:
        return []
    value = holdings["data"]["total_value"] * classified / 100
    moves = {c: round(-drift[c] / 100 * value) for c in CLASSES if abs(drift[c]) >= 1}
    over = [c for c in CLASSES if drift[c] >= 1]
    under = [c for c in CLASSES if drift[c] <= -1]
    detail = (f"{CLASS_LABEL[worst].capitalize()} are {current[worst]:.0f}% of your investments; your plan "
              f"says {target[worst]}%. ")
    detail += ("Move about " + ", ".join(f"{inr(-moves[c])} out of {CLASS_LABEL[c]}" for c in over)
               + " into " + " and ".join(CLASS_LABEL[c] for c in under) + ", or direct new money there first.")
    return [action("rebalance", "medium", "Rebalance towards your plan", detail, [holdings, plan],
                   "/investments", {"drift_pp": drift, "moves": moves})]


def concentration_actions(holdings: dict) -> list[dict]:
    """One action for every stock above CONCENTRATION_PCT of all holdings,
    combined into a single card when there are several."""
    if not is_usable(holdings):
        return []
    total = holdings["data"]["total_value"]
    heavy = [
        (h, h["current_value"] / total * 100) for h in holdings["data"]["holdings"]
        if h["asset_class"] == "equity" and h["current_value"] and total
        and h["current_value"] / total * 100 > CONCENTRATION_PCT
    ]
    if not heavy:
        return []
    heavy.sort(key=lambda pair: pair[1], reverse=True)
    shares = {h["instrument_id"]: round(share, 1) for h, share in heavy}
    if len(heavy) == 1:
        h, share = heavy[0]
        title = f"{h['name']} is {share:.0f}% of everything you've invested"
        detail = (f"One company above {CONCENTRATION_PCT:g}% means its bad news hits your whole portfolio. "
                  "Add to other holdings rather than this one.")
        link = f"/instrument/{h['instrument_id']}"
    else:
        listed = ", ".join(f"{h['name']} ({share:.0f}%)" for h, share in heavy)
        title = f"{len(heavy)} stocks are each over {CONCENTRATION_PCT:g}% of everything you've invested"
        detail = (f"{listed}. A company's bad news then hits your whole portfolio; spread new money "
                  "across other holdings instead.")
        link = "/investments"
    return [action("concentration", "medium", title, detail, [holdings], link,
                   {"share_pct": shares}, about=["You hold"])]


def review_actions(holdings: dict, sentiment: dict, sectors: dict) -> list[dict]:
    """Negative news AND a falling sector on a stock the user holds. A prompt
    to look, never a sell signal."""
    if not (is_usable(holdings) and is_usable(sentiment) and is_usable(sectors)):
        return []
    held = {r["instrument_id"].removeprefix("stock-") for r in holdings["data"]["holdings"]
            if r["asset_class"] == "equity"}
    sector_by_id = {s["sector"]: s for s in sectors["data"]["sectors"]}
    actions = []
    for s in sentiment["data"]["stocks"]:
        sector = sector_by_id.get(TICKER_TO_SECTOR.get(s["ticker"]))
        if (s["ticker"] in held and s["label"] == "negative" and sector
                and sector["change_1m"] is not None and sector["change_1m"] <= REVIEW_SECTOR_FALL_PCT):
            actions.append(action(
                "review_holding", "low", f"Review {s['name']}",
                f"Negative news this week ({s['article_count']} articles) and the {sector['name']} sector "
                f"is {sector['change_1m']:+.1f}% this month. Read the news before deciding; this is not "
                "a sell signal.",
                [sentiment, sectors], f"/instrument/stock-{s['ticker']}", {"ticker": s["ticker"]},
                about=[s["name"], f"{sector['name']} sector"],
            ))
    return actions


def not_in_plan_actions(holdings: dict, plan: dict) -> list[dict]:
    if not (is_usable(holdings) and is_usable(plan)):
        return []
    planned = {h["instrument_id"] for h in plan["data"]["holdings"]}
    extra = [h for h in holdings["data"]["holdings"] if h["instrument_id"] not in planned]
    if not extra:
        return []
    names = ", ".join(h["name"] for h in extra[:5]) + (f" and {len(extra) - 5} more" if len(extra) > 5 else "")
    return [action(
        "not_in_plan", "low",
        f"{len(extra)} of your holdings {'is' if len(extra) == 1 else 'are'}n't in your plan",
        f"{names}. There's no need to sell; just consider pointing new money at the plan instead.",
        [holdings, plan], "/portfolio-plan", {"instrument_ids": [h["instrument_id"] for h in extra]},
    )]


# --- Setup steps and the whole result ---------------------------------------------------

SETUP_STEPS = {
    "budget": ("Set up your budget", "Income, spending and emergency savings unlock the safety checks.", "/budget"),
    "risk_profile": ("Answer the risk questionnaire", "Needed before any investing advice.", "/portfolio-plan"),
    "portfolio_plan": ("Build a portfolio plan", "Tells the advisor what you're aiming for.", "/portfolio-plan"),
}


def setup_steps(by_id: dict[str, dict]) -> list[dict]:
    steps = []
    for module, (title, detail, link) in SETUP_STEPS.items():
        if by_id[module]["status"] == "not_set_up":
            steps.append({"module": module, "title": title, "detail": detail, "link": link})
    budget = by_id["budget"]
    if is_usable(budget) and budget["data"]["emergency_fund"]["status"] == "unknown":
        steps.append({"module": "budget", "title": "Add your emergency savings",
                      "detail": "So the advisor can check your safety net.", "link": "/budget"})
    return steps


def build_actions(modules: list[dict]) -> dict:
    by_id = {m["module"]: m for m in modules}
    safety = budget_actions(by_id["budget"])
    blocked = any(a["severity"] == "high" for a in safety)
    actions = [
        *safety,
        *goal_actions(by_id["goals"]),
        *invest_action(by_id["risk_profile"], by_id["portfolio_plan"], by_id["predictions"], blocked,
                       safety_checked=is_usable(by_id["budget"])),
        *rebalance_action(by_id["holdings"], by_id["portfolio_plan"]),
        *concentration_actions(by_id["holdings"]),
        *review_actions(by_id["holdings"], by_id["sentiment"], by_id["sectors"]),
        *not_in_plan_actions(by_id["holdings"], by_id["portfolio_plan"]),
    ]
    actions.sort(key=lambda a: a["priority"])
    used = sorted({c for a in actions for c in a["contributors"]})
    return {
        "actions": actions,
        "setup": setup_steps(by_id),
        "modules_used": used,
        "modules_unavailable": [m["module"] for m in modules if m["status"] == "unavailable"],
        "partial": any(m["status"] == "unavailable" for m in modules),
    }
