"""AI trade tasks as the API sees them (Phase 10, B11).

A request only queues a task in MongoDB and returns; the worker (B12) talks
to the chain. Approve, decline, withdraw and revoke go from the user's
wallet straight to the contracts, never through here.
"""

from datetime import UTC, datetime

from app.data import blockchain_repository as repo
from app.services.blockchain.formats import EvidenceStatus, Step

# Unfinished states keep `active` true. Final: pending_user is not final on
# chain, but the worker is done; the event reader moves it on.
STATES = (
    "queued",
    "opening",
    "evidence",
    "proposing",
    "pending_user",
    "executed",
    "rejected",
    "failed",
)


class TaskError(Exception):
    def __init__(self, status: int, detail: str) -> None:
        super().__init__(detail)
        self.status = status
        self.detail = detail


async def create_task(user_id: str, fund: str, ticker: str | None, horizon_days: int) -> dict:
    link = await repo.get_wallet_link(user_id)
    if link is None:
        raise TaskError(409, "Link a wallet first")
    now = datetime.now(UTC)
    doc = {
        "user_id": user_id,
        "wallet": link["address"],
        "fund": fund,
        "ticker": ticker,
        "horizon_days": horizon_days,
        "state": "queued",
        "active": True,
        "attempts": 0,
        "next_attempt_at": now,
        "lease_until": None,
        "task_id": None,
        "vault": None,
        "evidence": [],
        "proposal": None,
        "outcome": None,
        "reason": None,
        "amount_out": None,
        "last_error": None,
        "mock_advisor": True,  # until Phase 9's advisor replaces it (B20)
        "created_at": now,
        "updated_at": now,
    }
    doc_id = await repo.insert_task(doc)
    if doc_id is None:
        raise TaskError(409, f"An AI trade for {fund} is already in progress")
    doc["_id"] = doc_id
    return to_response(doc)


async def list_tasks(user_id: str) -> list[dict]:
    return [to_response(d) for d in await repo.list_tasks(user_id)]


async def get_task(user_id: str, doc_id: str) -> dict | None:
    doc = await repo.get_task(user_id, doc_id)
    return to_response(doc) if doc else None


def to_response(doc: dict) -> dict:
    return {
        "id": str(doc["_id"]),
        "fund": doc["fund"],
        "ticker": doc.get("ticker"),
        "state": doc["state"],
        "task_id": doc.get("task_id"),
        "vault": doc.get("vault"),
        "outcome": doc.get("outcome"),
        "reason": doc.get("reason"),
        "amount_out": doc.get("amount_out"),
        "evidence": [
            {
                "step": Step(e["step"]).name.lower(),
                "status": EvidenceStatus(e["status"]).name,
                "score": e["score"],
                "inputs": e.get("inputs", {}),
                "outputs": e.get("outputs", {}),
                "tx_hash": e.get("tx_hash"),
            }
            for e in doc.get("evidence", [])
        ],
        "proposal": _public_proposal(doc.get("proposal")),
        "last_error": doc.get("last_error"),
        "mock_advisor": doc.get("mock_advisor", True),
        "created_at": doc["created_at"],
        "updated_at": doc["updated_at"],
    }


def _public_proposal(record: dict | None) -> dict | None:
    """The owner sees their own explanation; the salt stays server-side."""
    if not record:
        return None
    return {k: v for k, v in record.items() if k != "salt"}
