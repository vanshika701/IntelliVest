"""Request and response shapes for /api/v1/blockchain (Phase 10)."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

Address = Field(pattern=r"^0x[0-9a-fA-F]{40}$")
FundLabel = Literal["tEquityFund", "tDebtFund", "tGoldFund"]


class ModelVersion(BaseModel):
    step: str
    name: str
    version: str
    key: str  # ModelRegistry key to accept in the mandate
    mock: bool = False


class BlockchainStatus(BaseModel):
    enabled: bool
    chain_id: int | None = None
    network: str | None = None
    contracts: dict[str, str] = {}
    models: list[ModelVersion] = []
    privacy_notice: str


class ChallengeRequest(BaseModel):
    address: str = Address


class ChallengeResponse(BaseModel):
    message: str
    expires_at: datetime


class VerifyRequest(BaseModel):
    address: str = Address
    signature: str = Field(pattern=r"^0x[0-9a-fA-F]{130}$")


class WalletResponse(BaseModel):
    address: str | None
    linked_at: datetime | None = None


class TaskCreate(BaseModel):
    fund: FundLabel
    # Stock whose stored prediction is the evidence; without one, stock
    # evidence is NO_DATA and the mandate decides.
    ticker: str | None = Field(default=None, pattern=r"^[A-Z0-9&\-]{1,20}$")
    horizon_days: int = Field(default=5, ge=1, le=250)


class EvidenceView(BaseModel):
    step: str
    status: str
    score: int
    inputs: dict
    outputs: dict
    tx_hash: str | None = None


class TaskResponse(BaseModel):
    id: str
    fund: str
    ticker: str | None
    state: str
    task_id: str | None = None
    vault: str | None = None
    outcome: str | None = None
    reason: str | None = None
    amount_out: str | None = None  # base units; can exceed 64 bits
    evidence: list[EvidenceView] = []
    proposal: dict | None = None
    last_error: str | None = None
    mock_advisor: bool = True
    created_at: datetime
    updated_at: datetime
