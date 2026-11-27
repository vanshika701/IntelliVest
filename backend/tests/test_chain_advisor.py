"""Phase 9 advisor behind the Phase 10 `Advisor` interface (B20): decisions
from stored advice, and proposals built by Phase 10's own build_proposal."""

from datetime import UTC, datetime, timedelta

import pytest

from app.services.advisor.chain_advisor import Phase9Advisor
from app.services.advisor.rules import build_actions
from app.services.blockchain.advisor import AdvisorRequest, build_proposal
from app.services.blockchain.formats import Evidence, EvidenceResult, EvidenceStatus, Side, Step
from tests.advisor_scenarios import SCENARIOS

U = 1_000_000  # token base units
TASK = bytes(range(32))


def advice_for(name: str, age_days: int = 0) -> dict:
    scenario = next(s for s in SCENARIOS if s.name == name)
    modules = scenario.results()
    return {"id": f"advice-{name}", "created_at": datetime.now(UTC) - timedelta(days=age_days),
            "modules": modules, **build_actions(modules)}


def request(cash: int, value: int, is_equity: bool = True, *evidence: EvidenceResult) -> AdvisorRequest:
    """`cash` and `value` in whole tINR; the fund is priced at 100 tINR a unit."""
    price = 100 * U
    return AdvisorRequest(
        task_id=TASK, vault="0x" + "bb" * 20, fund="0x" + "cc" * 20,
        fund_label="tEquityFund" if is_equity else "tDebtFund", is_equity=is_equity,
        price=price, cash=cash * U, units=value * U * U // price, max_slippage_bps=100, evidence=evidence,
    )


def stock_evidence(score: int) -> EvidenceResult:
    e = Evidence(TASK, int(Step.STOCK_PREDICTION), int(EvidenceStatus.OK),
                 bytes(32), bytes(32), bytes(32), bytes(32), score, 0, 252, 0)
    return EvidenceResult(e, {}, {})


async def test_buys_up_to_the_plan_share() -> None:
    decision = await Phase9Advisor(advice_for("ready_to_start")).decide(request(10_000, 0))
    assert decision.side == Side.BUY
    assert decision.amount == 4_500 * U  # 45% of the vault's 10,000 tINR
    assert decision.confidence == 10_000
    assert decision.contributions["rebalance"] == {"target_bps": 4500, "current_bps": 0, "band_bps": 500}
    assert "45% in stocks" in decision.explanation


async def test_sells_when_over_the_band() -> None:
    decision = await Phase9Advisor(advice_for("ready_to_start")).decide(request(2_000, 8_000))
    assert decision.side == Side.SELL
    assert decision.amount == 35 * U  # 3,500 tINR of units at 100 tINR each


async def test_no_trade_inside_the_band() -> None:
    assert await Phase9Advisor(advice_for("ready_to_start")).decide(request(5_300, 4_700)) is None


async def test_non_equity_fund_targets_debt_plus_gold() -> None:
    decision = await Phase9Advisor(advice_for("ready_to_start")).decide(request(10_000, 0, is_equity=False))
    assert decision.amount == 5_500 * U  # 45% debt + 10% gold


@pytest.mark.parametrize("name", ["no_safety_net", "overspender", "heavy_emis", "profile_but_no_plan", "new_user"])
async def test_no_trade_while_advice_says_to_wait(name: str) -> None:
    assert await Phase9Advisor(advice_for(name)).decide(request(10_000, 0)) is None


async def test_stale_plan_halves_confidence() -> None:
    decision = await Phase9Advisor(advice_for("stale_plan")).decide(request(10_000, 0))
    assert decision.confidence == 5_000


async def test_prediction_evidence_is_recorded_not_used() -> None:
    advisor = Phase9Advisor(advice_for("ready_to_start"))
    plain = await advisor.decide(request(10_000, 0))
    bullish = await advisor.decide(request(10_000, 0, True, stock_evidence(9_000)))
    assert (bullish.side, bullish.amount) == (plain.side, plain.amount)
    assert bullish.contributions["evidence"]["stock_prediction"] == {
        "status": "OK", "score": 9_000, "used_to_decide": False}


async def test_phase10_builds_a_proposal_from_the_decision() -> None:
    advisor = Phase9Advisor(advice_for("ready_to_start"))
    req = request(10_000, 0)
    decision = await advisor.decide(req)
    draft = build_proposal(req, decision, advisor, evidence_hash=bytes(32), nonce=1, deadline=2_000_000_000)
    assert draft.proposal.amount == 4_500 * U and draft.proposal.side == int(Side.BUY)
    assert draft.record["model"] == "intellivest/phase9-advisor"
    assert draft.record["explanation"]["contributions"]["portfolio_plan"]["equity_pct"] == 45
