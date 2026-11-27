"""Phase 9 advisor for Phase 10 (checklist B20): implements the `Advisor`
interface in app/services/blockchain/advisor.py, replacing the mock.

Phase 10 asks about one vault and one fund at a time. This advisor answers
from the user's stored advice (the same advice they see on the AI Advisor
page), so a vault trade never contradicts it:

- No trade while the advice has a high-severity safety action
  (overspending, no emergency fund, critical debt).
- No trade without a usable portfolio plan.
- Otherwise, move this fund towards the plan's share for its kind (stocks
  for an equity fund; debt plus gold for any other), only when it is at
  least REBALANCE_THRESHOLD_PP away: the same band as the rebalance advice.
  The vault shows only its cash and this fund, so shares are of that.
- Sentiment and stock-prediction evidence are recorded in the contributions
  but don't change the decision: Phase 4's backtest found its up/down calls
  no better than "always up" (docs/PHASE_4_PREDICTION.md).

Phase 10 builds, hashes and signs the proposal (build_proposal); this
class only decides. Everything it returns is an integer, as the hashing
requires. Confidence is in the inputs, not the outcome: fresh plan and
profile 10000, any stale 5000.
"""

from datetime import UTC, datetime

from app.core.advisor_config import ADVISOR_VERSION, REBALANCE_THRESHOLD_PP
from app.services.blockchain.advisor import AdvisorDecision, AdvisorRequest
from app.services.blockchain.formats import BPS, EvidenceStatus, Side, Step

PRICE_SCALE = 1_000_000  # request.price is tINR base units per whole fund unit
STATUS_CONFIDENCE = {"ok": BPS, "stale": BPS // 2}


def _module(advice: dict, module_id: str) -> dict | None:
    return next((m for m in advice["modules"] if m["module"] == module_id), None)


def _evidence(request: AdvisorRequest) -> dict:
    """What Phase 10 submitted, recorded but not used to decide."""
    out = {}
    for name, step in (("sentiment", Step.SENTIMENT), ("stock_prediction", Step.STOCK_PREDICTION)):
        result = request.step(step)
        if result is not None:
            out[name] = {"status": EvidenceStatus(result.evidence.status).name, "score": result.evidence.score,
                         "used_to_decide": False}
    return out


class Phase9Advisor:
    model_name = "intellivest/phase9-advisor"
    model_version = ADVISOR_VERSION

    def __init__(self, advice: dict) -> None:
        """`advice` is the vault owner's latest stored advice
        (advisor.service.get_latest_advice)."""
        self.advice = advice

    async def decide(self, request: AdvisorRequest) -> AdvisorDecision | None:
        blocking = [a["id"] for a in self.advice["actions"] if a["severity"] == "high"]
        if blocking:
            return None
        plan, risk = _module(self.advice, "portfolio_plan"), _module(self.advice, "risk_profile")
        if not plan or not risk or plan["status"] not in STATUS_CONFIDENCE or risk["status"] not in STATUS_CONFIDENCE:
            return None

        split = plan["data"]["split"]
        target_pct = split["equity"] if request.is_equity else split["debt"] + split["gold"]
        value = request.units * request.price // PRICE_SCALE
        total = request.cash + value
        if total <= 0:
            return None
        target_bps = target_pct * BPS // 100
        current_bps = value * BPS // total
        band_bps = int(REBALANCE_THRESHOLD_PP * BPS // 100)
        gap = total * target_bps // BPS - value  # tINR to add (+) or remove (-)

        if current_bps <= target_bps - band_bps and request.cash > 0:
            side, amount = Side.BUY, min(gap, request.cash)
        elif current_bps >= target_bps + band_bps and request.units > 0:
            side, amount = Side.SELL, min(-gap * PRICE_SCALE // request.price, request.units)
        else:
            return None
        if amount <= 0:
            return None

        confidence = min(STATUS_CONFIDENCE[plan["status"]], STATUS_CONFIDENCE[risk["status"]])
        verb = "buy" if side == Side.BUY else "sell"
        explanation = (
            f"Plan: {target_pct}% in {'stocks' if request.is_equity else 'debt and gold'}. "
            f"{request.fund_label} is {current_bps / 100:.1f}% of this vault's cash and fund, "
            f"{abs(current_bps - target_bps) / 100:.1f} points from the plan "
            f"(the band is {REBALANCE_THRESHOLD_PP:g}), so {verb} towards it."
        )
        age_days = (datetime.now(UTC) - _aware(self.advice["created_at"])).days
        return AdvisorDecision(
            side=side,
            amount=amount,
            confidence=confidence,
            explanation=explanation,
            contributions={
                "risk_profile": {"profile": risk["data"]["profile"], "status": risk["status"]},
                "portfolio_plan": {"equity_pct": split["equity"], "debt_pct": split["debt"],
                                   "gold_pct": split["gold"], "status": plan["status"]},
                "rebalance": {"target_bps": target_bps, "current_bps": current_bps, "band_bps": band_bps},
                "evidence": _evidence(request),
            },
            inputs={"advice_id": self.advice["id"], "advice_age_days": age_days,
                    "advisor_version": ADVISOR_VERSION},
        )


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=UTC)
