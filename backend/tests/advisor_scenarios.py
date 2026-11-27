"""Hand-written user situations for evaluating the Phase 9 advisor, with the
advice a careful planner would give first. Used by tests/test_advisor_eval.py
(runs every test run) and ml/evaluate_advisor.py (writes the metrics report).

Each scenario builds real module results with the real summarise functions,
from the kind of raw data a user of the app would actually have. The
expectations were written from the situation, before running the rules.
"""

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from app.core.advisor_config import MODULES
from app.core.budget_config import CATEGORY_BY_ID
from app.services.advisor.modules import (
    module_result,
    summarize_budget,
    summarize_goals,
    summarize_holdings,
    summarize_portfolio_plan,
    summarize_predictions,
    summarize_risk_profile,
    summarize_sectors,
    summarize_sentiment,
)
from app.services.budget_rules import analyze_budget
from app.services.health_score import health_score

NOW = datetime(2026, 11, 27, tzinfo=UTC)
PLAN_STOCKS = ["TCS.NS", "HDFCBANK.NS", "ITC.NS", "SUNPHARMA.NS"]


# --- Builders ----------------------------------------------------------------------

def budget(income: float, spend: dict, emergency_fund: float | None):
    # analyze_budget ignores unknown ids, which would silently drop spending.
    unknown = set(spend) - set(CATEGORY_BY_ID)
    assert not unknown, f"unknown budget categories: {unknown}"
    analysis = analyze_budget(income=income, spend=spend, emergency_fund=emergency_fund)
    return summarize_budget(analysis, health_score(analysis))


def risk(label: str, profile: str):
    return summarize_risk_profile({"profile": profile, "label": label, "capacity_score": 60.0,
                                   "tolerance_score": 55.0, "limited_by": "tolerance", "notes": [],
                                   "version": "risk-v1", "updated_at": NOW})


def plan(split=(45, 45, 10), lump=100_000, monthly=10_000, age_days=2, goal=None):
    each = split[0] / 100 / len(PLAN_STOCKS) if split[0] else 0
    holdings = [{"instrument_id": f"stock-{t}", "name": t, "asset_class": "equity", "kind": "stock",
                 "weight": each, "lump_sum_amount": round(lump * each), "monthly_amount": round(monthly * each)}
                for t in PLAN_STOCKS if each]
    for iid, name, cls, pct in (("mf-118987", "HDFC Corporate Bond Fund", "debt", split[1]),
                                ("mf-119788", "SBI Gold Fund", "gold", split[2])):
        if pct:
            holdings.append({"instrument_id": iid, "name": name, "asset_class": cls, "kind": "fund",
                             "weight": pct / 100, "lump_sum_amount": round(lump * pct / 100),
                             "monthly_amount": round(monthly * pct / 100)})
    return summarize_portfolio_plan({
        "id": "r1", "created_at": NOW - timedelta(days=age_days),
        "inputs": {"lump_sum": lump, "monthly_sip": monthly, "horizon_months": 84, "goal": goal},
        "allocation": {"equity_pct": split[0], "debt_pct": split[1], "gold_pct": split[2]},
        "profile": {"label": "Moderate"}, "versions": {"recommendation": "rec-v1"}, "holdings": holdings,
    }, NOW)


def holdings(*rows):
    """rows: (instrument_id, name, type, current value)"""
    items = [{"instrument_id": i, "instrument_name": n, "instrument_type": t, "current_value": v, "gain_pct": 0.0}
             for i, n, t, v in rows]
    return summarize_holdings({"holdings": items, "current_value": sum(r[3] for r in rows), "unvalued_count": 0})


def goals(*items):
    """items: (name, flat monthly, affordable?)"""
    built = []
    for i, (name, monthly, ok) in enumerate(items):
        afford = ({"status": "affordable", "message": "It fits."} if ok else
                  {"status": "not_affordable", "message": "It doesn't fit.", "gap": monthly / 2,
                   "options": [{"message": f"Extend {name} by 3 years to bring it within reach."}]})
        built.append({"id": f"g{i}", "name": name, "target_amount": monthly * 60, "horizon_months": 60,
                      "plan": {"summary": f"{name}: save monthly.", "flat": {"monthly": monthly}, "affordability": afford}})
    return summarize_goals({"items": built, "combined": None})


def market(wipro_label="neutral", it_change=2.0):
    snaps = [
        {"sector": "it", "name": "IT", "as_of": NOW, "trend": "down" if it_change < -2 else "up",
         "changes": {"1m": it_change}, "sentiment": {"label": wipro_label, "article_count": 14},
         "stocks": [{"ticker": "WIPRO.NS", "name": "Wipro", "sentiment_score": -0.35 if wipro_label == "negative" else 0.1,
                     "sentiment_label": wipro_label, "article_count": 11},
                    {"ticker": "TCS.NS", "name": "Tata Consultancy Services", "sentiment_score": 0.2,
                     "sentiment_label": "positive", "article_count": 30}]},
        {"sector": "banking", "name": "Banking", "as_of": NOW, "trend": "up", "changes": {"1m": 3.1},
         "sentiment": {"label": "neutral", "article_count": 40},
         "stocks": [{"ticker": "HDFCBANK.NS", "name": "HDFC Bank", "sentiment_score": 0.05,
                     "sentiment_label": "neutral", "article_count": 25}]},
    ]
    tickers = [*PLAN_STOCKS, "WIPRO.NS"]
    docs = {t: [{"horizon_days": 252, "low": -0.16, "mid": 0.09, "high": 0.38, "as_of": NOW, "model_version": "1.0.0"}]
            for t in tickers}
    return {"sectors": summarize_sectors(snaps, tickers, NOW), "sentiment": summarize_sentiment(snaps, tickers, NOW),
            "predictions": summarize_predictions(docs, 252, NOW)}


def missing(module: str):
    return module_result(module, "not_set_up", reason="Not set up.")


HEALTHY = {"housing": 25_000, "groceries": 9_000, "utilities": 4_000, "transportation": 4_000}


# --- Scenarios ---------------------------------------------------------------------

@dataclass
class Scenario:
    name: str
    story: str
    modules: dict
    first: str | None                 # action that must come first (None: no actions)
    include: list[str] = field(default_factory=list)
    exclude: list[str] = field(default_factory=list)
    setup: list[str] | None = None    # exact setup step titles, if checked

    def results(self) -> list[dict]:
        base = {m: missing(m) for m in MODULES} | market()
        return [{**base, **self.modules}[m] for m in MODULES]


def _healthy_budget():
    return budget(100_000, HEALTHY, 300_000)


SCENARIOS = [
    Scenario("new_user", "Just signed up; nothing entered.",
             {m: missing(m) for m in MODULES}, None,
             setup=["Set up your budget", "Answer the risk questionnaire", "Build a portfolio plan"]),
    Scenario("overspender", "Earns ₹40,000, spends ₹48,000 with lots of dining out, has a plan.",
             {"budget": budget(40_000, {"housing": 15_000, "food_dining": 18_000, "shopping_personal": 15_000}, 10_000),
              "risk_profile": risk("Moderate", "moderate"), "portfolio_plan": plan()},
             "spending_exceeds_income", include=["emergency_fund", "invest_per_plan"]),
    Scenario("no_safety_net", "Good income, no emergency savings, wants to start investing.",
             {"budget": budget(90_000, HEALTHY, 0), "risk_profile": risk("Moderate", "moderate"), "portfolio_plan": plan()},
             "emergency_fund", include=["invest_per_plan"]),
    Scenario("heavy_emis", "Car and personal loan EMIs take 45% of take-home pay.",
             {"budget": budget(80_000, {"housing": 15_000, "emi_debt": 36_000}, 300_000),
              "risk_profile": risk("Moderate", "moderate"), "portfolio_plan": plan()},
             "debt_critical", include=["invest_per_plan"], exclude=["debt_high"]),
    Scenario("moderate_emis", "Home-loan EMI is 32% of income: high but not critical.",
             {"budget": budget(100_000, {"housing": 10_000, "emi_debt": 32_000}, 400_000),
              "risk_profile": risk("Moderate", "moderate"), "portfolio_plan": plan()},
             "debt_high", exclude=["debt_critical"]),
    Scenario("ready_to_start", "Healthy budget and a plan, nothing invested yet.",
             {"budget": _healthy_budget(), "risk_profile": risk("Moderate", "moderate"), "portfolio_plan": plan()},
             "invest_per_plan", exclude=["rebalance", "emergency_fund"], setup=[]),
    Scenario("drifted_after_rally", "Stocks rallied: 75% of the portfolio vs a 45% plan.",
             {"budget": _healthy_budget(), "risk_profile": risk("Moderate", "moderate"), "portfolio_plan": plan(),
              "holdings": holdings(("stock-TCS.NS", "TCS", "STOCK", 25_000.0), ("stock-HDFCBANK.NS", "HDFC Bank", "STOCK", 25_000.0),
                                   ("stock-ITC.NS", "ITC", "STOCK", 25_000.0), ("mf-118987", "HDFC Corporate Bond Fund", "MF", 25_000.0))},
             "invest_per_plan", include=["rebalance", "concentration"]),
    Scenario("on_target", "Invested roughly per plan (46/44/10).",
             {"budget": _healthy_budget(), "risk_profile": risk("Moderate", "moderate"), "portfolio_plan": plan(),
              "holdings": holdings(("stock-TCS.NS", "TCS", "STOCK", 11_500.0), ("stock-HDFCBANK.NS", "HDFC Bank", "STOCK", 11_500.0),
                                   ("stock-ITC.NS", "ITC", "STOCK", 11_500.0), ("stock-SUNPHARMA.NS", "Sun Pharma", "STOCK", 11_500.0),
                                   ("mf-118987", "HDFC Corporate Bond Fund", "MF", 44_000.0), ("mf-119788", "SBI Gold Fund", "MF", 10_000.0))},
             "invest_per_plan", exclude=["rebalance", "concentration", "not_in_plan"]),
    Scenario("all_in_one_stock", "Everything in a single stock that isn't in the plan.",
             {"budget": _healthy_budget(), "risk_profile": risk("Moderate", "moderate"), "portfolio_plan": plan(),
              "holdings": holdings(("stock-WIPRO.NS", "Wipro", "STOCK", 200_000.0))},
             "invest_per_plan", include=["rebalance", "concentration", "not_in_plan"]),
    Scenario("bad_news_falling_sector", "Holds Wipro; negative news this week and IT down 7% in a month.",
             {"budget": _healthy_budget(), "risk_profile": risk("Moderate", "moderate"), "portfolio_plan": plan(),
              "holdings": holdings(("stock-WIPRO.NS", "Wipro", "STOCK", 10_000.0), ("mf-118987", "HDFC Corporate Bond Fund", "MF", 90_000.0)),
              **market(wipro_label="negative", it_change=-7.0)},
             "invest_per_plan", include=["review_holding"]),
    Scenario("bad_news_rising_sector", "Holds Wipro; negative news but IT up 2%: not enough to flag.",
             {"budget": _healthy_budget(), "risk_profile": risk("Moderate", "moderate"), "portfolio_plan": plan(),
              "holdings": holdings(("stock-WIPRO.NS", "Wipro", "STOCK", 10_000.0), ("mf-118987", "HDFC Corporate Bond Fund", "MF", 90_000.0)),
              **market(wipro_label="negative", it_change=2.0)},
             "invest_per_plan", exclude=["review_holding"]),
    Scenario("goal_out_of_reach", "Wants a ₹30 lakh house in 5 years on a ₹20,000 surplus.",
             {"budget": budget(60_000, {"housing": 20_000, "groceries": 8_000}, 200_000),
              "goals": goals(("House", 50_000.0, False), ("Holiday", 3_000.0, True)),
              "risk_profile": risk("Moderate", "moderate"), "portfolio_plan": plan()},
             "goal_unaffordable", include=["invest_per_plan"]),
    Scenario("stale_plan", "Plan built 40 days ago; prices have moved since.",
             {"budget": _healthy_budget(), "risk_profile": risk("Moderate", "moderate"), "portfolio_plan": plan(age_days=40)},
             "invest_per_plan"),
    Scenario("short_horizon_conservative", "Saving for a car in 2 years: no stocks in the plan.",
             {"budget": _healthy_budget(), "risk_profile": risk("Conservative", "conservative"),
              "portfolio_plan": plan(split=(0, 95, 5), lump=200_000, monthly=0)},
             "invest_per_plan"),
    Scenario("mystery_funds", "Most money in funds we can't classify: drift isn't judged.",
             {"budget": _healthy_budget(), "risk_profile": risk("Moderate", "moderate"), "portfolio_plan": plan(),
              "holdings": holdings(("stock-TCS.NS", "TCS", "STOCK", 20_000.0), ("mf-555", "ABC Flexi Cap Fund", "MF", 80_000.0))},
             "invest_per_plan", include=["concentration"], exclude=["rebalance"]),
    Scenario("profile_but_no_plan", "Answered the questionnaire but hasn't built a plan.",
             {"budget": _healthy_budget(), "risk_profile": risk("Moderate", "moderate")},
             None, exclude=["invest_per_plan"], setup=["Build a portfolio plan"]),
    Scenario("everything_wrong", "Overspending, no savings, critical EMIs and a drifted portfolio.",
             {"budget": budget(50_000, {"housing": 12_000, "emi_debt": 25_000, "food_dining": 18_000}, 0),
              "risk_profile": risk("Moderate", "moderate"), "portfolio_plan": plan(),
              "holdings": holdings(("stock-TCS.NS", "TCS", "STOCK", 80_000.0), ("mf-118987", "HDFC Corporate Bond Fund", "MF", 20_000.0))},
             "spending_exceeds_income", include=["emergency_fund", "debt_critical", "rebalance"]),
    Scenario("savings_not_entered", "Budget set up but emergency savings left blank.",
             {"budget": budget(100_000, HEALTHY, None), "risk_profile": risk("Moderate", "moderate"), "portfolio_plan": plan()},
             "invest_per_plan", setup=["Add your emergency savings"]),
]

# Required order inside "everything_wrong": the planning sequence.
EVERYTHING_WRONG_ORDER = ["spending_exceeds_income", "emergency_fund", "debt_critical"]


# --- Checks (shared by the tests and ml/evaluate_advisor.py) --------------------------

import json
import re

from app.services.advisor.rules import build_actions
from app.services.budget_rules import inr

_RUPEES = re.compile(r"₹[\d,]+")


def expectation_failures(scenario: Scenario) -> list[str]:
    result = build_actions(scenario.results())
    ids = [a["id"] for a in result["actions"]]
    failures = []
    if scenario.first is None and ids:
        failures.append(f"expected no actions, got {ids}")
    if scenario.first is not None and (not ids or ids[0] != scenario.first):
        failures.append(f"expected {scenario.first} first, got {ids[:1]}")
    failures += [f"missing {i}" for i in scenario.include if i not in ids]
    failures += [f"should not include {i}" for i in scenario.exclude if i in ids]
    if scenario.setup is not None and [s["title"] for s in result["setup"]] != scenario.setup:
        failures.append(f"setup {[s['title'] for s in result['setup']]} != {scenario.setup}")
    if scenario.name == "everything_wrong" and [i for i in ids if i in EVERYTHING_WRONG_ORDER] != EVERYTHING_WRONG_ORDER:
        failures.append(f"planning order broken: {ids}")
    return failures


def _amounts_in(value) -> set[str]:
    """Every ₹ amount a module or action records, formatted as the user sees it."""
    found: set[str] = set()
    if isinstance(value, bool):
        return found
    if isinstance(value, int | float):
        found.add(inr(abs(value)))
    elif isinstance(value, str):
        found |= set(_RUPEES.findall(value))
    elif isinstance(value, dict):
        for v in value.values():
            found |= _amounts_in(v)
    elif isinstance(value, list | tuple):
        for v in value:
            found |= _amounts_in(v)
    return found


def untraced_amounts(result: dict, modules: list[dict]) -> list[str]:
    """₹ figures shown in an action that aren't recorded in its own data or
    its contributors' facts and data."""
    by_id = {m["module"]: m for m in modules}
    problems = []
    for a in result["actions"]:
        sources = _amounts_in(a["data"]) | _amounts_in(a["facts"])
        for c in a["contributors"]:
            sources |= _amounts_in(by_id[c]["data"]) | _amounts_in(by_id[c]["facts"])
        for shown in _RUPEES.findall(a["title"] + " " + a["detail"]):
            if shown not in sources:
                problems.append(f"{a['id']}: {shown}")
    return problems


def degradation_failures(scenario: Scenario) -> list[str]:
    """Knock each usable module out in turn: advice must still build, be
    marked partial, and never cite the missing module."""
    failures = []
    base = scenario.results()
    for i, m in enumerate(base):
        if m["status"] not in ("ok", "stale"):
            continue
        broken = [*base[:i], module_result(m["module"], "unavailable", reason="down"), *base[i + 1:]]
        try:
            result = build_actions(broken)
        except Exception as exc:  # noqa: BLE001 — any exception is the failure being measured
            failures.append(f"{m['module']} down: raised {exc!r}")
            continue
        if not result["partial"] or m["module"] not in result["modules_unavailable"]:
            failures.append(f"{m['module']} down: not reported as partial")
        cited = [a["id"] for a in result["actions"] if m["module"] in a["contributors"]]
        if cited:
            failures.append(f"{m['module']} down: still cited by {cited}")
        json.dumps(result, default=str)  # stays storable
    return failures
