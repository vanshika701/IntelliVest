"""What any advisor (mock, rules, LLM, trained) gives Phase 10 (B10).

The advisor decides off-chain and returns an `AdvisorDecision`. This module
turns it into the frozen `Proposal`, adding the hashes, nonce and deadline,
so an advisor never handles hashing or keys. Phase 9 (B20) plugs in here by
implementing `Advisor`.
"""

from dataclasses import dataclass, field
from typing import Protocol

from app.services.blockchain import hashing
from app.services.blockchain.formats import BPS, EvidenceResult, Proposal, Side, Step


@dataclass(frozen=True)
class AdvisorRequest:
    """One task: one vault, one fund. Amounts are token base units (6 decimals)."""

    task_id: bytes
    vault: str
    fund: str
    fund_label: str  # e.g. "tEquityFund"
    is_equity: bool
    price: int  # tINR base units per whole fund unit
    cash: int  # tINR in the vault
    units: int  # fund units in the vault
    max_slippage_bps: int  # from the mandate
    evidence: tuple[EvidenceResult, ...] = ()

    def step(self, step: Step) -> EvidenceResult | None:
        return next((e for e in self.evidence if e.evidence.step == step), None)


@dataclass(frozen=True)
class AdvisorDecision:
    side: Side
    amount: int  # tINR for a BUY, fund units for a SELL
    confidence: int  # 0..10000
    explanation: str
    # Which module contributed what, for the evidence view and Phase 9.
    contributions: dict = field(default_factory=dict)
    # Whatever else the advisor used; may hold private data, so it is salted.
    inputs: dict = field(default_factory=dict)


class Advisor(Protocol):
    model_name: str
    model_version: str

    async def decide(self, request: AdvisorRequest) -> AdvisorDecision | None:
        """None means no trade; the task is left to expire."""
        ...


@dataclass(frozen=True)
class ProposalDraft:
    """A proposal ready to sign, plus the off-chain record its hashes cover."""

    proposal: Proposal
    record: dict  # store in MongoDB; holds the salt


def proposal_nonce(task_id: bytes) -> int:
    """One proposal per task: task IDs are unique, so this never repeats, and
    resending a task's proposal is refused as a replay."""
    return int.from_bytes(task_id, "big")


def expected_out(side: Side, amount: int, price: int) -> int:
    """MockFundMarket.swap before skew."""
    return amount * 1_000_000 // price if side == Side.BUY else amount * price // 1_000_000


def build_proposal(
    request: AdvisorRequest,
    decision: AdvisorDecision,
    advisor: Advisor,
    evidence_hash: bytes,
    nonce: int,
    deadline: int,
) -> ProposalDraft:
    if not 0 <= decision.confidence <= BPS:
        raise ValueError("confidence must be 0..10000")
    if decision.amount <= 0:
        raise ValueError("amount must be positive")
    minimum = expected_out(decision.side, decision.amount, request.price)
    minimum = minimum * (BPS - request.max_slippage_bps) // BPS
    salt = hashing.new_salt()
    inputs = {
        "fund": request.fund_label,
        "price": request.price,
        "cash": request.cash,
        "units": request.units,
        "evidence": [_evidence_ref(e) for e in request.evidence],
        "advisor": decision.inputs,
    }
    explanation = {"text": decision.explanation, "contributions": decision.contributions}
    proposal = Proposal(
        taskId=request.task_id,
        vault=request.vault,
        fund=request.fund,
        side=int(decision.side),
        amount=decision.amount,
        minimumReceived=minimum,
        confidence=decision.confidence,
        modelId=hashing.model_id(advisor.model_name),
        modelVersion=hashing.model_id(advisor.model_version),
        inputHash=hashing.hash_private(inputs, salt),
        evidenceHash=evidence_hash,
        explanationHash=hashing.hash_private(explanation, salt),
        nonce=nonce,
        deadline=deadline,
    )
    record = {
        "model": advisor.model_name,
        "model_version": advisor.model_version,
        "inputs": inputs,
        "explanation": explanation,
        "salt": salt,
    }
    return ProposalDraft(proposal, record)


def _evidence_ref(result: EvidenceResult) -> dict:
    e = result.evidence
    return {
        "step": e.step,
        "status": e.status,
        "score": e.score,
        "output_hash": "0x" + e.outputHash.hex(),
    }
