"""Phase 9 rules engine: each rule's trigger and non-trigger, ordering,
traceability and partial results. Module results are built with the real
summarise functions from realistic raw inputs."""

from datetime import UTC, datetime, timedelta

import pytest

from app.core.advisor_config import MODULES, PRIORITY
from app.services.advisor.modules import (
    is_usable,
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
from app.services.advisor.rules import build_actions
from app.services.budget_rules import analyze_budget
from app.services.health_score import health_score

NOW = datetime(2026, 11, 27, tzinfo=UTC)
PLAN_STOCKS = ["TCS.NS", "HDFCBANK.NS", "WIPRO.NS"]


def budget(income=100_000, spend=None, emergency_fund=300_000):
    spend = {"housing": 25_000, "groceries": 10_000} if spend is None else spend
    analysis = analyze_budget(income=income, spend=spend, emergency_fund=emergency_fund)
    return summarize_budget(analysis, health_score(analysis))


def risk(label="Moderate", profile="moderate"):
    return summarize_risk_profile({"profile": profile, "label": label, "capacity_score": 70.0,
                                   "tolerance_score": 55.0, "limited_by": "tolerance", "notes": [],
                                   "version": "risk-v1", "updated_at": NOW})


def plan(split=(45, 45, 10), lump=100_000, monthly=10_000, age_days=1):
    equity_each = split[0] / 100 / len(PLAN_STOCKS)
    holdings = [{"instrument_id": f"stock-{t}", "name": t, "asset_class": "equity", "kind": "stock",
                 "weight": equity_each, "lump_sum_amount": 1, "monthly_amount": 1} for t in PLAN_STOCKS]
    holdings += [
        {"instrument_id": "mf-118987", "name": "HDFC Corporate Bond", "asset_class": "debt", "kind": "fund",
         "weight": split[1] / 100, "lump_sum_amount": 1, "monthly_amount": 1},
        {"instrument_id": "mf-119788", "name": "SBI Gold Fund", "asset_class": "gold", "kind": "fund",
         "weight": split[2] / 100, "lump_sum_amount": 1, "monthly_amount": 1},
    ]
    return summarize_portfolio_plan({
        "id": "r1", "created_at": NOW - timedelta(days=age_days),
        "inputs": {"lump_sum": lump, "monthly_sip": monthly, "horizon_months": 84, "goal": None},
        "allocation": {"equity_pct": split[0], "debt_pct": split[1], "gold_pct": split[2]},
        "profile": {"label": "Moderate"}, "versions": {"recommendation": "rec-v1"}, "holdings": holdings,
    }, NOW)


def holdings(rows):
    """rows: (instrument_id, name, type, value)"""
    items = [{"instrument_id": i, "instrument_name": n, "instrument_type": t, "current_value": v, "gain_pct": 0.0}
             for i, n, t, v in rows]
    return summarize_holdings({"holdings": items, "current_value": sum(r[3] for r in rows), "unvalued_count": 0})


def snapshots(wipro_label="negative", it_change=-6.2):
    return [{
        "sector": "it", "name": "IT", "as_of": NOW, "trend": "down", "changes": {"1m": it_change},
        "sentiment": {"label": "negative", "article_count": 12},
        "stocks": [
            {"ticker": "WIPRO.NS", "name": "Wipro", "sentiment_score": -0.3, "sentiment_label": wipro_label, "article_count": 9},
            {"ticker": "TCS.NS", "name": "Tata Consultancy Services", "sentiment_score": 0.2,
             "sentiment_label": "positive", "article_count": 20},
        ],
    }]


def predictions(tickers=PLAN_STOCKS):
    docs = {t: [{"horizon_days": 252, "low": -0.15, "mid": 0.08, "high": 0.35, "as_of": NOW, "model_version": "v1"}]
            for t in tickers}
    return summarize_predictions(docs, 252, NOW)


def modules(**overrides) -> list[dict]:
    """A complete, healthy user unless overridden; missing ones are not set up."""
    defaults = {
        "budget": budget(), "goals": module_result("goals", "not_set_up", reason="none"),
        "risk_profile": risk(), "portfolio_plan": plan(),
        "holdings": module_result("holdings", "not_set_up", reason="none"),
        "sectors": summarize_sectors(snapshots(), PLAN_STOCKS, NOW),
        "sentiment": summarize_sentiment(snapshots(), PLAN_STOCKS, NOW),
        "predictions": predictions(),
    }
    defaults |= overrides
    return [defaults[m] for m in MODULES]


def ids(result: dict) -> list[str]:
    return [a["id"] for a in result["actions"]]


def check_traceable(result: dict, mods: list[dict]) -> None:
    usable = {m["module"] for m in mods if is_usable(m)}
    for a in result["actions"]:
        assert a["facts"], f"{a['id']} must rest on facts"
        assert set(a["contributors"]) <= usable, f"{a['id']} used a module that wasn't usable"
        assert a["priority"] == PRIORITY[a["id"]]
    assert [a["priority"] for a in result["actions"]] == sorted(a["priority"] for a in result["actions"])


# --- Scenarios -------------------------------------------------------------------------

def test_healthy_user_with_a_plan_just_invests() -> None:
    mods = modules()
    result = build_actions(mods)
    check_traceable(result, mods)
    assert ids(result) == ["invest_per_plan"]
    invest = result["actions"][0]
    assert invest["severity"] == "medium"
    assert "₹1,00,000 now and ₹10,000 a month" in invest["title"]
    assert "45% stocks, 45% debt, 10% gold" in invest["detail"]
    assert invest["data"]["equity_range_1y"] == (-13.9, 41.9)  # from the stored log-return ranges
    assert "predictions" in invest["contributors"]
    assert result["setup"] == [] and result["partial"] is False


def test_spending_more_than_income_comes_first_and_holds_back_investing() -> None:
    mods = modules(budget=budget(income=50_000, spend={"housing": 30_000, "food_dining": 25_000}))
    result = build_actions(mods)
    check_traceable(result, mods)
    assert ids(result)[0] == "spending_exceeds_income"
    assert "₹5,000 a month more than you earn" in result["actions"][0]["title"]
    invest = next(a for a in result["actions"] if a["id"] == "invest_per_plan")
    assert invest["severity"] == "low" and "once the steps above" in invest["detail"]


def test_emergency_fund_shortfall_with_time_to_fill() -> None:
    mods = modules(budget=budget(emergency_fund=40_000))  # essentials 35,000 -> 3 months is 1,05,000
    action = build_actions(mods)["actions"][0]
    assert action["id"] == "emergency_fund"
    assert action["data"]["shortfall"] == pytest.approx(65_000)
    assert action["data"]["months_to_fill"] == pytest.approx(round(65_000 / 65_000, 1))
    assert "₹65,000 to go" in action["title"]
    assert build_actions(modules(budget=budget(emergency_fund=200_000)))["actions"][0]["id"] != "emergency_fund"


@pytest.mark.parametrize(("emi", "expected"), [(40_000, "debt_critical"), (32_000, "debt_high"), (20_000, None)])
def test_emi_levels(emi: int, expected: str | None) -> None:
    result = build_actions(modules(budget=budget(spend={"housing": 20_000, "emi_debt": emi})))
    debt = [a for a in ids(result) if a.startswith("debt_")]
    assert debt == ([expected] if expected else [])


def test_unaffordable_goal() -> None:
    goal_plan = {"summary": "s", "flat": {"monthly": 40_000.0},
                 "affordability": {"status": "not_affordable", "message": "m", "gap": 15_000.0,
                                   "options": [{"message": "Extend the timeline to 7 years."}]}}
    goals = summarize_goals({"items": [{"id": "g1", "name": "House", "target_amount": 2_000_000,
                                        "horizon_months": 48, "plan": goal_plan}], "combined": None})
    action = next(a for a in build_actions(modules(goals=goals))["actions"] if a["id"] == "goal_unaffordable")
    assert '"House" needs ₹40,000 a month' in action["title"]
    assert action["detail"] == "Extend the timeline to 7 years."


def test_rebalance_when_drift_passes_the_threshold() -> None:
    held = holdings([("stock-TCS.NS", "TCS", "STOCK", 70_000.0), ("mf-118987", "HDFC Corporate Bond", "MF", 20_000.0),
                     ("mf-119788", "SBI Gold Fund", "MF", 10_000.0)])
    action = next(a for a in build_actions(modules(holdings=held))["actions"] if a["id"] == "rebalance")
    assert action["data"]["drift_pp"] == {"equity": 25.0, "debt": -25.0, "gold": 0.0}
    assert action["data"]["moves"] == {"equity": -25_000, "debt": 25_000}
    assert "Stocks are 70% of your investments; your plan says 45%" in action["detail"]


def test_no_rebalance_inside_the_band_or_when_unclassified() -> None:
    close = holdings([("stock-TCS.NS", "TCS", "STOCK", 48_000.0), ("mf-118987", "HDFC Corporate Bond", "MF", 42_000.0),
                      ("mf-119788", "SBI Gold Fund", "MF", 10_000.0)])
    assert "rebalance" not in ids(build_actions(modules(holdings=close)))
    unknown = holdings([("stock-TCS.NS", "TCS", "STOCK", 70_000.0), ("mf-3", "Mystery Flexi Cap", "MF", 30_000.0)])
    assert "rebalance" not in ids(build_actions(modules(holdings=unknown)))


def test_concentration() -> None:
    held = holdings([("stock-TCS.NS", "TCS", "STOCK", 20_000.0), ("mf-118987", "HDFC Corporate Bond", "MF", 80_000.0)])
    action = next(a for a in build_actions(modules(holdings=held))["actions"] if a["id"] == "concentration")
    assert action["title"] == "TCS is 20% of everything you've invested"
    assert action["link"] == "/instrument/stock-TCS.NS"
    assert action["data"]["share_pct"] == {"stock-TCS.NS": 20.0}


def test_several_concentrated_stocks_share_one_card() -> None:
    held = holdings([("stock-TCS.NS", "TCS", "STOCK", 30_000.0), ("stock-ITC.NS", "ITC", "STOCK", 20_000.0),
                     ("mf-118987", "HDFC Corporate Bond", "MF", 50_000.0)])
    found = [a for a in build_actions(modules(holdings=held))["actions"] if a["id"] == "concentration"]
    assert len(found) == 1
    assert found[0]["title"] == "2 stocks are each over 15% of everything you've invested"
    assert found[0]["detail"].startswith("TCS (30%), ITC (20%).")


def _held_wipro():
    return holdings([("stock-WIPRO.NS", "Wipro", "STOCK", 10_000.0), ("mf-118987", "HDFC Corporate Bond", "MF", 90_000.0)])


def test_review_needs_negative_news_and_a_falling_sector() -> None:
    action = next(a for a in build_actions(modules(holdings=_held_wipro()))["actions"] if a["id"] == "review_holding")
    assert action["title"] == "Review Wipro" and "not a sell signal" in action["detail"]
    assert all("Wipro" in f or "IT sector" in f for f in action["facts"])  # only the relevant facts
    assert set(action["contributors"]) == {"sentiment", "sectors"}

    def reviews(**kw):
        snap = snapshots(**kw)
        return [a for a in build_actions(modules(
            holdings=_held_wipro(), sectors=summarize_sectors(snap, PLAN_STOCKS, NOW),
            sentiment=summarize_sentiment(snap, PLAN_STOCKS, NOW)))["actions"] if a["id"] == "review_holding"]

    assert reviews(wipro_label="positive") == []
    assert reviews(it_change=-3.0) == []  # a small sector dip alone isn't enough


def test_holdings_outside_the_plan() -> None:
    held = holdings([("stock-ITC.NS", "ITC", "STOCK", 5_000.0), ("mf-118987", "HDFC Corporate Bond", "MF", 5_000.0)])
    action = next(a for a in build_actions(modules(holdings=held))["actions"] if a["id"] == "not_in_plan")
    assert action["title"] == "1 of your holdings isn't in your plan"
    assert action["data"]["instrument_ids"] == ["stock-ITC.NS"]


# --- Missing and failing modules ---------------------------------------------------------

def test_new_user_gets_setup_steps_not_advice() -> None:
    blank = {m: module_result(m, "not_set_up", reason="none") for m in MODULES}
    result = build_actions([blank[m] for m in MODULES])
    assert result["actions"] == []
    assert [s["module"] for s in result["setup"]] == ["budget", "risk_profile", "portfolio_plan"]


def test_missing_emergency_savings_is_a_setup_step() -> None:
    steps = build_actions(modules(budget=budget(emergency_fund=None)))["setup"]
    assert steps == [{"module": "budget", "title": "Add your emergency savings",
                      "detail": "So the advisor can check your safety net.", "link": "/budget"}]


def test_unavailable_module_marks_the_advice_partial() -> None:
    down = module_result("predictions", "unavailable", reason="timed out")
    mods = modules(predictions=down)
    result = build_actions(mods)
    check_traceable(result, mods)
    assert result["partial"] is True and result["modules_unavailable"] == ["predictions"]
    invest = result["actions"][0]
    assert invest["data"]["equity_range_1y"] is None and "predictions" not in invest["contributors"]


def test_investing_without_a_budget_says_the_safety_checks_were_skipped() -> None:
    invest = build_actions(modules(budget=module_result("budget", "not_set_up", reason="none")))["actions"][0]
    assert invest["id"] == "invest_per_plan"
    assert "couldn't check your emergency fund or debts" in invest["detail"]
    assert "couldn't check" not in build_actions(modules())["actions"][0]["detail"]


def test_stale_plan_is_used_but_flagged() -> None:
    invest = build_actions(modules(portfolio_plan=plan(age_days=40)))["actions"][0]
    assert "over a month old" in invest["detail"]


def test_no_range_when_too_few_planned_stocks_have_predictions() -> None:
    invest = build_actions(modules(predictions=predictions(["TCS.NS"])))["actions"][0]
    assert invest["data"]["equity_range_1y"] is None
