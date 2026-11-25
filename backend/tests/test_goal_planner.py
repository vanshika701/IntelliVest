"""Unit tests for the SIP maths in goal_planner (pure functions)."""

import pytest

from app.services.goal_planner import (
    flat_factor,
    plan_goal,
    required_flat_sip,
    required_step_up_start,
    step_up_factor,
    step_up_schedule,
)


def _fv_by_simulation(monthly_amounts: list[float], annual_pct: float) -> float:
    """Month-by-month simulation: deposit at the start, then grow one month."""
    i = annual_pct / 100 / 12
    balance = 0.0
    for amount in monthly_amounts:
        balance = (balance + amount) * (1 + i)
    return balance


def test_flat_factor_matches_known_value() -> None:
    # ₹10,000/month for 10 years at 12%: the standard annuity-due result ≈ ₹23,23,391.
    assert 10_000 * flat_factor(120, 12) == pytest.approx(2_323_391, abs=1)


def test_flat_factor_zero_return_is_simple_sum() -> None:
    assert flat_factor(36, 0) == 36
    assert required_flat_sip(36_000, 36, 0) == pytest.approx(1_000)


def test_required_flat_sip_reaches_target() -> None:
    sip = required_flat_sip(800_000, 36, 7)
    assert _fv_by_simulation([sip] * 36, 7) == pytest.approx(800_000, rel=1e-9)


def test_step_up_with_zero_step_equals_flat() -> None:
    assert step_up_factor(60, 10, 0) == pytest.approx(flat_factor(60, 10))


def test_step_up_start_reaches_target_including_partial_year() -> None:
    months, rate, step = 30, 8, 10  # 2.5 years: last year is only 6 months
    start = required_step_up_start(500_000, months, rate, step)
    amounts = [start * 1.1 ** (m // 12) for m in range(months)]
    assert _fv_by_simulation(amounts, rate) == pytest.approx(500_000, rel=1e-9)
    assert start < required_flat_sip(500_000, months, rate)


def test_step_up_zero_return() -> None:
    # 24 months, 0%: 12x + 12x(1.1) = 25.2x = 25,200 -> x = 1,000
    assert required_step_up_start(25_200, 24, 0, 10) == pytest.approx(1_000)


def test_step_up_schedule_years_and_months() -> None:
    rows = step_up_schedule(1_000, 30, 10)
    assert [r["months"] for r in rows] == [12, 12, 6]
    assert [r["monthly"] for r in rows] == [1_000, 1_100, 1_210]


def test_very_short_horizon_one_month() -> None:
    plan = plan_goal("Phone", 20_000, 1)
    # One deposit that grows for one month at the default short-horizon rate (6%).
    assert plan["flat"]["monthly"] == pytest.approx(20_000 / (1 + 0.06 / 12), abs=0.01)
    assert plan["step_up"]["start_monthly"] == plan["flat"]["monthly"]
    assert any("year or less" in n for n in plan["notes"])


def test_default_return_depends_on_horizon() -> None:
    assert plan_goal("A", 1e5, 24)["assumption"]["annual_return_pct"] == 6
    assert plan_goal("B", 1e5, 48)["assumption"]["annual_return_pct"] == 8
    assert plan_goal("C", 1e5, 120)["assumption"]["annual_return_pct"] == 11
    custom = plan_goal("D", 1e5, 120, annual_return_pct=8)["assumption"]
    assert custom["annual_return_pct"] == 8 and custom["is_default"] is False


def test_short_horizon_gets_safer_instrument_note() -> None:
    assert any("recurring deposits" in n for n in plan_goal("Car", 8e5, 36)["notes"])
    assert not any("recurring deposits" in n for n in plan_goal("Retire", 8e5, 120)["notes"])


def test_summary_sentence() -> None:
    plan = plan_goal("Car", 800_000, 36)
    assert plan["summary"].startswith("To reach ₹8,00,000 in 3 years you can start a ₹")
    assert "step up 10% each year" in plan["summary"]


def test_affordable_when_surplus_covers_sip() -> None:
    plan = plan_goal("Car", 800_000, 36, monthly_surplus=50_000)
    assert plan["affordability"]["status"] == "affordable"


def test_unaffordable_suggests_options_with_amounts() -> None:
    overspent = [
        {"category": "food_dining", "name": "Food & Dining Out", "overspend_amount": 4_000},
        {"category": "shopping_personal", "name": "Shopping & Personal Care", "overspend_amount": 3_000},
    ]
    plan = plan_goal("Car", 800_000, 36, monthly_surplus=15_000, overspent=overspent)
    aff = plan["affordability"]
    assert aff["status"] == "not_affordable"
    types = [o["type"] for o in aff["options"]]
    assert types == ["extend_timeline", "reduce_target", "free_up"]

    extend = aff["options"][0]
    assert extend["horizon_months"] > 36 and extend["monthly"] <= 15_000
    reduce = aff["options"][1]
    assert reduce["target_amount"] == pytest.approx(15_000 * flat_factor(36, 6), abs=0.01)
    free = aff["options"][2]
    assert free["total"] <= aff["gap"] + 0.01
    assert free["cuts"][0]["amount"] == 4_000


def test_no_surplus_and_unknown_budget() -> None:
    assert plan_goal("X", 1e5, 24, monthly_surplus=-2_000)["affordability"]["status"] == "not_affordable"
    assert plan_goal("X", 1e5, 24)["affordability"]["status"] == "unknown"


def test_step_up_is_offered_when_only_its_start_fits() -> None:
    plan = plan_goal("Car", 800_000, 60, monthly_surplus=9_500)
    assert plan["flat"]["monthly"] > 9_500 >= plan["step_up"]["start_monthly"]
    option = plan["affordability"]["options"][0]
    assert option["type"] == "step_up" and option["monthly"] == plan["step_up"]["start_monthly"]


def test_committed_goals_reduce_what_is_available() -> None:
    plan = plan_goal("Car", 800_000, 36, monthly_surplus=25_000, committed=10_000)
    assert plan["affordability"]["status"] == "not_affordable"
    assert plan["affordability"]["available"] == 15_000
