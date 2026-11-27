"""Phase 9 evaluation, run on every test run: hand-written situations with
expected advice, each module knocked out in turn, and every ₹ figure traced
to its source. ml/evaluate_advisor.py writes the same checks as a report."""

import pytest

from app.services.advisor.rules import build_actions
from tests.advisor_scenarios import (
    SCENARIOS,
    degradation_failures,
    expectation_failures,
    untraced_amounts,
)

IDS = [s.name for s in SCENARIOS]


def test_enough_distinct_scenarios() -> None:
    assert len(SCENARIOS) >= 15 and len(set(IDS)) == len(IDS)


@pytest.mark.parametrize("scenario", SCENARIOS, ids=IDS)
def test_expected_advice(scenario) -> None:
    assert expectation_failures(scenario) == [], scenario.story


@pytest.mark.parametrize("scenario", SCENARIOS, ids=IDS)
def test_degrades_cleanly(scenario) -> None:
    assert degradation_failures(scenario) == []


@pytest.mark.parametrize("scenario", SCENARIOS, ids=IDS)
def test_every_amount_is_traceable(scenario) -> None:
    modules = scenario.results()
    assert untraced_amounts(build_actions(modules), modules) == []


def test_every_rule_is_exercised() -> None:
    from app.core.advisor_config import PRIORITY

    seen = {a["id"] for s in SCENARIOS for a in build_actions(s.results())["actions"]}
    assert seen == set(PRIORITY), f"rules never triggered: {set(PRIORITY) - seen}"


# --- The checks themselves catch mistakes ----------------------------------------------

def test_expectations_catch_a_wrong_priority_order(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.core import advisor_config

    swapped = {**advisor_config.PRIORITY, "invest_per_plan": 1}  # investing before the safety net
    monkeypatch.setattr("app.services.advisor.rules.PRIORITY", swapped)
    failing = [s.name for s in SCENARIOS if expectation_failures(s)]
    assert {"no_safety_net", "overspender", "heavy_emis", "everything_wrong"} <= set(failing)


def test_traceability_catches_an_invented_amount() -> None:
    scenario = next(s for s in SCENARIOS if s.name == "no_safety_net")
    modules = scenario.results()
    result = build_actions(modules)
    result["actions"][0]["detail"] += " You could also save ₹12,34,567."
    assert untraced_amounts(result, modules) == ["emergency_fund: ₹12,34,567"]


def test_degradation_catches_citing_a_missing_module(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.services.advisor import rules

    real = rules.invest_action

    def always_cites_predictions(risk, plan, predictions, blocked, safety_checked):
        out = real(risk, plan, predictions, blocked, safety_checked)
        for a in out:
            a["contributors"] = sorted({*a["contributors"], "predictions"})
        return out

    monkeypatch.setattr(rules, "invest_action", always_cites_predictions)
    scenario = next(s for s in SCENARIOS if s.name == "ready_to_start")
    assert "predictions down: still cited by ['invest_per_plan']" in degradation_failures(scenario)
