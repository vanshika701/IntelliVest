"""Phase 9 module interface: pure summaries, the timeout/error wrapper, and
the two-round gather against the test DB."""

import asyncio
from datetime import UTC, datetime, timedelta

import pytest

from app.core import advisor_config
from app.core.advisor_config import MODULES
from app.core.risk_config import QUESTIONS
from app.services.advisor import adapters
from app.services.advisor.modules import (
    asset_class,
    freshness,
    is_usable,
    run_module,
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
from app.services.risk_profile_service import save_risk_profile

NOW = datetime(2026, 11, 27, tzinfo=UTC)
STATUSES = {"ok", "stale", "not_set_up", "unavailable", "not_built"}


def assert_shape(result: dict) -> None:
    assert result["module"] in MODULES and result["status"] in STATUSES
    assert (result["label"], result["phase"]) == MODULES[result["module"]]
    assert isinstance(result["facts"], list) and isinstance(result["data"], dict)
    if not is_usable(result):
        assert result["reason"], "a module that can't be used must say why"


# --- Pure summaries -----------------------------------------------------------

def test_budget_summary() -> None:
    analysis = analyze_budget(
        income=100_000, spend={"housing": 30_000, "groceries": 10_000, "emi_debt": 45_000},
        emergency_fund=20_000,
    )
    result = summarize_budget(analysis, health_score(analysis))
    assert_shape(result)
    data = result["data"]
    assert data["emi"]["status"] == "critical"  # 45% of income
    assert data["emergency_fund"]["status"] == "partial"
    assert data["emergency_fund"]["shortfall"] == pytest.approx(3 * 85_000 - 20_000)
    assert any("EMI" in f or "Loan" in f for f in result["facts"])
    assert summarize_budget(None, None)["status"] == "not_set_up"


def test_goals_summary() -> None:
    plan = {"summary": "Start ₹5,000/month.", "flat": {"monthly": 5000.0},
            "affordability": {"status": "affordable", "message": "It fits."}}
    goals = {"items": [{"id": "g1", "name": "Car", "target_amount": 300_000, "horizon_months": 48, "plan": plan}],
             "combined": None}
    result = summarize_goals(goals)
    assert_shape(result)
    assert result["data"]["goals"][0]["affordability"] == "affordable"
    assert result["facts"] == ["Car: Start ₹5,000/month. It fits."]
    assert summarize_goals({"items": []})["status"] == "not_set_up"


def test_risk_profile_summary() -> None:
    profile = {"profile": "moderate", "label": "Moderate", "capacity_score": 62.5, "tolerance_score": 50.0,
               "limited_by": "tolerance", "notes": [], "version": "risk-v1", "updated_at": NOW}
    result = summarize_risk_profile(profile)
    assert_shape(result)
    assert result["data"]["profile"] == "moderate" and result["version"] == "risk-v1"
    assert summarize_risk_profile(None)["status"] == "not_set_up"


def _rec(created_at: datetime) -> dict:
    return {
        "id": "r1", "created_at": created_at, "inputs": {"horizon_months": 84, "goal": None},
        "allocation": {"equity_pct": 45, "debt_pct": 45, "gold_pct": 10},
        "profile": {"label": "Moderate"}, "versions": {"recommendation": "rec-v1"},
        "holdings": [
            {"instrument_id": "stock-TCS.NS", "name": "TCS", "asset_class": "equity", "kind": "stock",
             "weight": 0.45, "lump_sum_amount": 4500, "monthly_amount": 0},
            {"instrument_id": "mf-118987", "name": "HDFC Corporate Bond", "asset_class": "debt", "kind": "fund",
             "weight": 0.55, "lump_sum_amount": 5500, "monthly_amount": 0},
        ],
    }


def test_portfolio_plan_summary_and_staleness() -> None:
    fresh = summarize_portfolio_plan(_rec(NOW - timedelta(days=2)), NOW)
    assert_shape(fresh)
    assert fresh["status"] == "ok"
    assert fresh["data"]["split"] == {"equity": 45, "debt": 45, "gold": 10}
    assert fresh["data"]["stock_tickers"] == ["TCS.NS"]
    old = summarize_portfolio_plan(_rec(NOW - timedelta(days=45)), NOW)
    assert old["status"] == "stale" and "30 days" in old["reason"]
    assert is_usable(old)  # stale data is still used, just flagged
    assert summarize_portfolio_plan(None, NOW)["status"] == "not_set_up"


@pytest.mark.parametrize(
    ("holding", "expected"),
    [
        ({"instrument_type": "STOCK", "instrument_id": "stock-TCS.NS", "instrument_name": "TCS"}, "equity"),
        ({"instrument_type": "MF", "instrument_id": "mf-119788", "instrument_name": "SBI GOLD FUND"}, "gold"),
        ({"instrument_type": "MF", "instrument_id": "mf-119091", "instrument_name": "HDFC Liquid Fund"}, "debt"),
        ({"instrument_type": "MF", "instrument_id": "mf-1", "instrument_name": "XYZ Gilt Fund"}, "debt"),
        ({"instrument_type": "ETF", "instrument_id": "mf-2", "instrument_name": "Gold BeES"}, "gold"),
        ({"instrument_type": "MF", "instrument_id": "mf-3", "instrument_name": "XYZ Flexi Cap Fund"}, "unclassified"),
    ],
)
def test_asset_class(holding: dict, expected: str) -> None:
    assert asset_class(holding) == expected


def test_holdings_summary() -> None:
    portfolio = {
        "current_value": 10_000.0, "unvalued_count": 1,
        "holdings": [
            {"instrument_id": "stock-TCS.NS", "instrument_name": "TCS", "instrument_type": "STOCK",
             "current_value": 6_000.0, "gain_pct": 5.0},
            {"instrument_id": "mf-119091", "instrument_name": "HDFC Liquid", "instrument_type": "MF",
             "current_value": 4_000.0, "gain_pct": 1.0},
            {"instrument_id": "mf-3", "instrument_name": "Mystery Fund", "instrument_type": "MF",
             "current_value": None, "gain_pct": None},
        ],
    }
    result = summarize_holdings(portfolio)
    assert_shape(result)
    assert result["data"]["split_pct"] == {"equity": 60.0, "debt": 40.0}
    assert result["data"]["stock_tickers"] == ["TCS.NS"]
    assert any("couldn't be valued" in f for f in result["facts"])
    assert summarize_holdings({"holdings": []})["status"] == "not_set_up"


def _snapshot(as_of: datetime) -> dict:
    return {
        "sector": "it", "name": "IT", "as_of": as_of.replace(tzinfo=None), "trend": "down",
        "changes": {"1m": -6.2}, "sentiment": {"label": "negative", "article_count": 12},
        "stocks": [{"ticker": "WIPRO.NS", "name": "Wipro", "sentiment_score": -0.31,
                    "sentiment_label": "negative", "article_count": 9}],
    }


def test_sector_and_sentiment_summaries() -> None:
    snaps = [_snapshot(NOW - timedelta(days=1))]
    sectors = summarize_sectors(snaps, ["WIPRO.NS"], NOW)
    assert_shape(sectors)
    assert sectors["data"]["sectors"][0]["trend"] == "down"
    assert "-6.2% over 1 month" in sectors["facts"][0]
    sentiment = summarize_sentiment(snaps, ["WIPRO.NS", "TCS.NS"], NOW)
    assert_shape(sentiment)
    assert [s["ticker"] for s in sentiment["data"]["stocks"]] == ["WIPRO.NS"]  # TCS isn't in the rollup
    assert "negative news" in sentiment["facts"][0]

    stale = summarize_sentiment([_snapshot(NOW - timedelta(days=10))], ["WIPRO.NS"], NOW)
    assert stale["status"] == "stale"
    assert summarize_sectors([], ["WIPRO.NS"], NOW)["status"] == "unavailable"
    assert summarize_sentiment(snaps, [], NOW)["status"] == "not_set_up"


def test_prediction_summary_uses_ranges_only() -> None:
    doc = {"horizon_days": 252, "low": -0.2, "mid": 0.1, "high": 0.4, "chance_up": 0.7, "rank": 1,
           "as_of": NOW - timedelta(days=1), "model_version": "stock-v1"}
    result = summarize_predictions({"TCS.NS": [doc]}, 252, NOW)
    assert_shape(result)
    row = result["data"]["stocks"][0]
    assert (row["low_pct"], row["mid_pct"], row["high_pct"]) == (-18.1, 10.5, 49.2)  # from log returns
    assert "chance_up" not in row and "rank" not in row
    assert "between -18.1% and +49.2%" in result["facts"][0]
    assert summarize_predictions({"TCS.NS": []}, 252, NOW)["status"] == "unavailable"
    assert summarize_predictions({}, 252, NOW)["status"] == "not_set_up"


def test_freshness() -> None:
    assert freshness("sectors", NOW - timedelta(days=7), NOW) == ("ok", None)
    assert freshness("sectors", NOW - timedelta(days=8), NOW)[0] == "stale"
    assert freshness("budget", NOW - timedelta(days=999), NOW) == ("ok", None)  # no age limit
    assert freshness("sectors", (NOW - timedelta(days=1)).replace(tzinfo=None), NOW)[0] == "ok"


# --- The wrapper ------------------------------------------------------------------

async def test_run_module_turns_errors_into_a_status() -> None:
    async def broken() -> dict:
        raise RuntimeError("database down")

    result = await run_module("budget", broken)
    assert_shape(result)
    assert result["status"] == "unavailable" and "server log" in result["reason"]
    assert "database down" not in result["reason"]  # internals stay in the log


async def test_run_module_times_out(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.services.advisor.modules.MODULE_TIMEOUT_SECONDS", 0.05)

    async def slow() -> dict:
        await asyncio.sleep(1)
        return {}

    result = await run_module("goals", slow)
    assert result["status"] == "unavailable" and "0.05 seconds" in result["reason"]
    assert result["elapsed_ms"] < 900
    assert advisor_config.MODULE_TIMEOUT_SECONDS == 5.0  # the real setting is untouched


# --- Two-round gather (test DB) -------------------------------------------------

async def test_new_user_gets_every_module_back(mongo_test_db) -> None:
    results = await adapters.gather_modules("user-without-data", NOW)
    assert [r["module"] for r in results] == list(MODULES)
    for r in results:
        assert_shape(r)
    statuses = {r["module"]: r["status"] for r in results}
    assert statuses["budget"] == statuses["risk_profile"] == statuses["holdings"] == "not_set_up"
    assert statuses["predictions"] == "not_set_up"  # no stocks to ask about


async def test_one_failing_module_doesn_t_stop_the_others(
    mongo_test_db, monkeypatch: pytest.MonkeyPatch
) -> None:
    await save_risk_profile("u1", {q.id: q.options[-1].id for q in QUESTIONS})

    async def broken(_user_id: str) -> dict:
        raise ConnectionError("prices service down")

    monkeypatch.setattr(adapters, "holdings", broken)
    statuses = {r["module"]: r["status"] for r in await adapters.gather_modules("u1", NOW)}
    assert statuses["holdings"] == "unavailable"
    assert statuses["risk_profile"] == "ok"
