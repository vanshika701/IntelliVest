"""A fixed-rule stand-in for the Phase 9 advisor (B10; replaced in B20).

Results produced with it must be labelled mock. It only reads the evidence
in the request, so the contract's checks can be tested end to end.
"""

from app.services.blockchain.advisor import AdvisorDecision, AdvisorRequest
from app.services.blockchain.formats import BPS, EvidenceStatus, Side, Step

BUY_SHARE_BPS = 1000  # buy with 10% of the cash
SELL_SHARE_BPS = 2500  # sell 25% of the units
SIGNAL_THRESHOLD = 1000  # how far from neutral before acting, out of 10000


class MockAdvisor:
    model_name = "intellivest/mock-advisor"
    model_version = "1"

    async def decide(self, request: AdvisorRequest) -> AdvisorDecision | None:
        signals: dict[str, int] = {}
        stock = request.step(Step.STOCK_PREDICTION)
        if stock and stock.evidence.status == EvidenceStatus.OK:
            # chance of "up" 0..10000 -> -10000..10000
            signals["stock_prediction"] = (stock.evidence.score - BPS // 2) * 2
        sentiment = request.step(Step.SENTIMENT)
        if sentiment and sentiment.evidence.status == EvidenceStatus.OK:
            signals["sentiment"] = sentiment.evidence.score
        if not signals:
            return None

        signal = sum(signals.values()) // len(signals)
        confidence = min(BPS, BPS // 2 + abs(signal) // 2)
        contributions = {name: {"signal": value} for name, value in signals.items()}
        if signal >= SIGNAL_THRESHOLD and request.cash > 0:
            side, amount = Side.BUY, request.cash * BUY_SHARE_BPS // BPS
        elif signal <= -SIGNAL_THRESHOLD and request.units > 0:
            side, amount = Side.SELL, request.units * SELL_SHARE_BPS // BPS
        else:
            return None
        if amount <= 0:
            return None
        return AdvisorDecision(
            side=side,
            amount=amount,
            confidence=confidence,
            explanation=(
                f"Mock rule: average signal {signal} of {', '.join(sorted(signals))}; "
                f"{side.name.lower()} {request.fund_label}."
            ),
            contributions=contributions,
            inputs={"signal": signal},
        )
