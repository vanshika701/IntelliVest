"""Unit tests for the deterministic rules engine (pure functions)."""

import pytest

from app.services.budget_rules import analyze_budget, improve_focus, inr

INCOME = 100_000


def _cat(result: dict, cat_id: str) -> dict:
    return next(c for c in result["categories"] if c["category"] == cat_id)


def test_inr_indian_grouping() -> None:
    assert inr(800000) == "₹8,00,000"
    assert inr(12345678) == "₹1,23,45,678"
    assert inr(999) == "₹999"
    # Half-up on the 2-dp value, like the UI (banker's rounding gave ₹18,133 here).
    assert inr(18133.4999) == "₹18,134"
    assert inr(18133.5) == "₹18,134"
    assert inr(18134.5) == "₹18,135"
    assert inr(-2500.5) == "-₹2,501"


def test_within_benchmark() -> None:
    result = analyze_budget(INCOME, {"food_dining": 5_000})
    row = _cat(result, "food_dining")
    assert row["status"] == "within"
    assert row["pct_of_income"] == 5
    assert row["overspend_amount"] == 0


def test_over_benchmark_with_amount_and_target() -> None:
    result = analyze_budget(INCOME, {"food_dining": 9_000})
    row = _cat(result, "food_dining")
    assert row["status"] == "over"
    assert row["overspend_amount"] == 3_000  # cap is 6% = ₹6,000
    assert row["suggested_target"] == 6_000
    assert row["message"] == (
        "You're spending 9% of income on Food & Dining Out (₹9,000/month); the recommended "
        "range is 3-6%. You're overspending by ₹3,000/month. Suggested target: ₹6,000."
    )


def test_under_range_is_not_flagged() -> None:
    assert _cat(analyze_budget(INCOME, {"groceries": 2_000}), "groceries")["status"] == "under"


def test_no_benchmark_categories() -> None:
    assert _cat(analyze_budget(INCOME, {"education": 40_000}), "education")["status"] == "no_benchmark"


def test_debt_over_guideline_and_critical() -> None:
    assert _cat(analyze_budget(INCOME, {"emi_debt": 32_000}), "emi_debt")["status"] == "over"
    critical = _cat(analyze_budget(INCOME, {"emi_debt": 40_000}), "emi_debt")
    assert critical["status"] == "critical"
    assert "36%" in critical["message"]


def test_savings_below_target() -> None:
    row = _cat(analyze_budget(INCOME, {"savings_investments": 10_000}), "savings_investments")
    assert row["status"] == "below_target"
    assert row["suggested_target"] == 20_000


def test_fifty_thirty_twenty_buckets() -> None:
    spend = {"housing": 40_000, "groceries": 15_000, "food_dining": 10_000, "travel": 25_000}
    result = analyze_budget(INCOME, spend)
    buckets = {b["bucket"]: b for b in result["buckets"]}
    assert buckets["needs"]["amount"] == 55_000 and buckets["needs"]["status"] == "over"
    assert buckets["wants"]["amount"] == 35_000 and buckets["wants"]["status"] == "over"
    assert buckets["savings"]["amount"] == 10_000 and buckets["savings"]["status"] == "below_target"
    assert result["savings_rate_pct"] == 10
    assert result["surplus"] == 10_000


def test_overspent_sorted_by_amount_and_improve_lists_others() -> None:
    spend = {"food_dining": 12_000, "travel": 6_000, "shopping_personal": 16_000, "entertainment": 6_000}
    result = analyze_budget(INCOME, spend)
    assert result["overspent"] == ["shopping_personal", "food_dining", "entertainment", "travel"]
    assert result["total_overspend"] == 10_000 + 6_000 + 1_000 + 1_000

    focus = improve_focus(result, "food_dining")
    assert focus["focus_category"]["overspend_amount"] == 6_000
    assert [o["category"] for o in focus["other_overspends"]] == ["shopping_personal", "entertainment", "travel"]


def test_compare_against_own_estimate() -> None:
    result = analyze_budget(INCOME, {"food_dining": 9_000}, estimates={"food_dining": 5_000}, basis="actual")
    assert _cat(result, "food_dining")["vs_estimate"] == 4_000
    assert "₹4,000 more than your own estimate of ₹5,000" in improve_focus(result, "food_dining")["summary"]


def test_emergency_fund_states() -> None:
    spend = {"housing": 30_000, "groceries": 10_000}  # essentials ₹40,000
    assert analyze_budget(INCOME, spend)["emergency_fund"]["status"] == "unknown"
    assert analyze_budget(INCOME, spend, emergency_fund=0)["emergency_fund"]["status"] == "missing"
    partial = analyze_budget(INCOME, spend, emergency_fund=80_000)["emergency_fund"]
    assert partial["status"] == "partial" and partial["months_covered"] == 2
    assert partial["shortfall"] == 40_000
    assert analyze_budget(INCOME, spend, emergency_fund=150_000)["emergency_fund"]["status"] == "adequate"


def test_zero_income_does_not_crash() -> None:
    result = analyze_budget(0, {"food_dining": 5_000})
    row = _cat(result, "food_dining")
    assert row["status"] == "no_income" and row["pct_of_income"] is None
    assert result["savings_rate_pct"] is None
    assert result["warnings"]
    assert improve_focus(result, "all")["summary"]


def test_missing_spend_data_is_all_zero() -> None:
    result = analyze_budget(INCOME, {})
    assert result["total_spend"] == 0
    assert result["overspent"] == []
    assert improve_focus(result, "all")["summary"] == "Your budget fits the 50/30/20 guideline."


def test_over_allocation_warning() -> None:
    result = analyze_budget(INCOME, {"housing": 60_000, "food_dining": 20_000, "savings_investments": 30_000})
    assert result["surplus"] == pytest.approx(20_000)
    assert "more than your income" in result["warnings"][0]
