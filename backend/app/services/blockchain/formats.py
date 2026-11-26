"""Enums and message shapes shared with blockchain/contracts/Types.sol.

The numbers are the Solidity enum positions, so the order must never change.
"""

from dataclasses import asdict, dataclass
from enum import IntEnum

BPS = 10_000  # scores, confidence and percentages are integers out of this
TOKEN_UNIT = 1_000_000  # every test token has 6 decimals
MAX_EVIDENCE_AGE_SECONDS = 7 * 24 * 3600  # AITaskManager.MAX_EVIDENCE_AGE
MAX_TASK_SECONDS = 7 * 24 * 3600  # AITaskManager.MAX_TASK_LENGTH


class Step(IntEnum):
    NONE = 0
    SENTIMENT = 1
    STOCK_PREDICTION = 2
    ADVISOR = 3


class EvidenceStatus(IntEnum):
    OK = 0
    NO_DATA = 1
    FALLBACK = 2


class Side(IntEnum):
    BUY = 0
    SELL = 1


class Outcome(IntEnum):
    NONE = 0
    OPEN = 1
    PENDING_USER = 2
    EXECUTED = 3
    REJECTED = 4


class Reason(IntEnum):
    NONE = 0
    NO_MANDATE = 1
    OUTSIDE_DATES = 2
    AI_PAUSED = 3
    FUND_NOT_ALLOWED = 4
    BAD_AMOUNT = 5
    OVER_TRADE_CAP = 6
    OVER_DAILY_CAP = 7
    OVER_MONTHLY_CAP = 8
    TOO_MANY_TRADES = 9
    OVER_EQUITY_LIMIT = 10
    STALE_PRICE = 11
    LOSS_LIMIT = 12
    MODEL_INACTIVE = 13
    MODEL_NOT_ACCEPTED = 14
    MISSING_EVIDENCE = 15
    NO_DATA_NOT_ALLOWED = 16
    EVIDENCE_MISMATCH = 17
    EVIDENCE_STALE = 18
    EXPIRED = 19
    EXECUTION_FAILED = 20
    USER_DECLINED = 21


@dataclass(frozen=True)
class Evidence:
    taskId: bytes
    step: int
    status: int
    modelId: bytes
    modelVersion: bytes
    inputHash: bytes
    outputHash: bytes
    score: int
    count: int
    horizonDays: int
    asOf: int

    def message(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class Proposal:
    taskId: bytes
    vault: str
    fund: str
    side: int
    amount: int
    minimumReceived: int
    confidence: int
    modelId: bytes
    modelVersion: bytes
    inputHash: bytes
    evidenceHash: bytes
    explanationHash: bytes
    nonce: int
    deadline: int

    def message(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class EvidenceResult:
    """One evidence step: the signed on-chain part and the off-chain details
    (stored in MongoDB) that its input and output hashes cover."""

    evidence: Evidence
    inputs: dict
    outputs: dict
