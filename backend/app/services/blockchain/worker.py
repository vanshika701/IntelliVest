"""Background worker for AI trade tasks (Phase 10, B12).

Moves each queued task through: find vault -> open on chain -> submit
evidence -> ask the advisor -> submit the proposal. The event reader
(events.py) then records the outcome. HTTP requests never wait for this.

Safe to stop at any point:
- Every transaction is signed and its hash saved before it is sent. After a
  restart the worker looks the hash up, or resends the same bytes; one
  nonce means it can only be mined once.
- Evidence and proposals are also checked on chain before sending.
- A lease stops two workers taking the same task. Run one worker per relayer
  key, since they would share its nonces.
"""

import asyncio
import logging
from datetime import UTC, datetime, timedelta

from app.core.config import settings
from app.data import blockchain_repository as repo
from app.services.blockchain import hashing
from app.services.blockchain.advisor import Advisor, AdvisorRequest, build_proposal, proposal_nonce
from app.services.blockchain.client import ChainClient, ChainError
from app.services.blockchain.formats import Evidence, EvidenceResult, Outcome, Step
from app.services.blockchain.mock_advisor import MockAdvisor
from app.services.blockchain.sentiment_evidence import sentiment_evidence
from app.services.blockchain.stock_evidence import stock_evidence

logger = logging.getLogger(__name__)

TASK_SECONDS = 3600  # time to collect evidence and propose
APPROVAL_SECONDS = 24 * 3600  # how long the owner has to approve
STEP_TIMEOUT_SECONDS = 180
LEASE_SECONDS = 600
MAX_ATTEMPTS = 6
FUNDS = ("tEquityFund", "tDebtFund", "tGoldFund")


def backoff(attempts: int) -> timedelta:
    return timedelta(seconds=min(15 * 2 ** max(attempts - 1, 0), 600))


def safe_error(exc: BaseException, rpc_url: str) -> str:
    """Error text for the database and logs, without the RPC URL (it can
    hold a provider key)."""
    text = f"{type(exc).__name__}: {exc}"[:300]
    return text.replace(rpc_url, "<rpc>") if rpc_url else text


class Worker:
    def __init__(self, client: ChainClient, advisor: Advisor | None = None) -> None:
        self.client = client
        self.advisor = advisor or MockAdvisor()

    async def run_due(self, limit: int = 5, now: datetime | None = None) -> int:
        """Advances up to `limit` due tasks; returns how many it took."""
        done = 0
        while done < limit:
            now_ = now or datetime.now(UTC)
            doc = await repo.claim_next_task(now_, now_ + timedelta(seconds=LEASE_SECONDS))
            if doc is None:
                break
            done += 1
            await self._run_one(doc, now_)
        return done

    async def _run_one(self, doc: dict, now: datetime) -> None:
        try:
            await asyncio.wait_for(self.advance(doc), STEP_TIMEOUT_SECONDS)
        except Exception as exc:  # noqa: BLE001 - any failure is retried, then recorded
            attempts = doc.get("attempts", 0) + 1
            error = safe_error(exc, self.client.config.rpc_url)
            logger.warning("Chain task %s attempt %d failed: %s", doc["_id"], attempts, error)
            fields = {
                "attempts": attempts,
                "last_error": error,
                "lease_until": None,
                "updated_at": now,
            }
            if attempts >= MAX_ATTEMPTS:
                fields |= {"state": "failed", "active": False}
            else:
                fields["next_attempt_at"] = now + backoff(attempts)
            await repo.update_task(doc["_id"], fields)

    # --- Steps ---

    async def advance(self, doc: dict) -> None:
        """Runs the task as far as it can go, saving after each step."""
        if doc["state"] == "queued":
            await self._find_vault(doc)
        if doc["state"] == "opening":
            await self._open(doc)
        if doc["state"] == "evidence":
            if await self._expired(doc):
                return
            await self._evidence(doc)
        if doc["state"] == "proposing":
            if await self._expired(doc):
                return
            await self._propose(doc)

    async def _save(self, doc: dict, fields: dict, push: dict | None = None) -> None:
        fields = fields | {"updated_at": datetime.now(UTC)}
        await repo.update_task(doc["_id"], fields, push)
        doc.update(fields)
        if push:
            for key, value in push.items():
                doc.setdefault(key, []).append(value)

    async def _finish(self, doc: dict, state: str, error: str | None = None) -> None:
        await self._save(
            doc, {"state": state, "active": False, "lease_until": None, "last_error": error}
        )

    async def _find_vault(self, doc: dict) -> None:
        if doc["fund"] not in FUNDS:
            return await self._finish(doc, "failed", f"Unknown fund {doc['fund']}")
        vault = await self.client.vault_of(doc["wallet"])
        if vault is None:
            return await self._finish(doc, "failed", "Create a vault first")
        await self._save(doc, {"vault": vault, "state": "opening"})

    async def _open(self, doc: dict) -> None:
        fund = self.client.config.contracts[doc["fund"]]
        if not doc.get("deadline"):
            await self._save(doc, {"deadline": await self.client.now() + TASK_SECONDS})
        manager = self.client.contract("AITaskManager")
        call = manager.functions.openTask(doc["vault"], fund, doc["deadline"])
        receipt = await self._transact(doc, "open", call)
        task_id = self.client.task_opened(receipt)
        await self._save(doc, {"task_id": "0x" + task_id.hex(), "state": "evidence"})

    async def _expired(self, doc: dict) -> bool:
        if await self.client.now() <= doc["deadline"]:
            return False
        await self._finish(doc, "expired", "Ran out of time before the proposal was sent")
        return True

    async def _evidence(self, doc: dict) -> None:
        task_id = bytes.fromhex(doc["task_id"][2:])
        recorded = {e["step"] for e in doc.get("evidence", [])}
        for step, role, build in self.evidence_steps(doc, task_id):
            if step in recorded:
                continue
            action = f"evidence-{step}"
            pending = doc.get("pending_tx")
            if pending and pending["action"] == action:
                # Sent before a restart: finish it with the details saved alongside.
                receipt = await self._transact(doc, action, None)
                draft = doc["pending_evidence"]
            elif await self.client.evidence_present(task_id, step):
                # On chain but not here (should not happen); the event reader has it.
                receipt, draft = None, {"step": step, "status": 0, "score": 0, "recovered": True}
            else:
                result = await build()
                signed = self.client.signer(role).sign_evidence(result.evidence)
                draft = _evidence_record(result)
                call = self.client.evidence_call(signed)
                receipt = await self._transact(doc, action, call, {"pending_evidence": draft})
            if receipt is not None:
                draft = draft | {"tx_hash": "0x" + bytes(receipt["transactionHash"]).hex()}
            await self._save(doc, {"pending_evidence": None}, {"evidence": draft})
        await self._save(doc, {"state": "proposing"})

    def evidence_steps(self, doc: dict, task_id: bytes) -> list:
        """(step, signing role, async builder) for each step with a registered version."""
        steps = []
        sentiment_version = settings.blockchain_sentiment_model_version
        if sentiment_version:

            async def sentiment() -> EvidenceResult:
                chain_now = datetime.fromtimestamp(await self.client.now(), UTC)
                ticker = doc.get("ticker") or ""
                return await sentiment_evidence(task_id, ticker, sentiment_version, chain_now)

            steps.append((int(Step.SENTIMENT), "sentiment", sentiment))
        version = settings.blockchain_stock_model_version
        if version:

            async def stock() -> EvidenceResult:
                chain_now = datetime.fromtimestamp(await self.client.now(), UTC)
                ticker = doc.get("ticker") or ""
                return await stock_evidence(
                    task_id, ticker, doc["horizon_days"], version, chain_now
                )

            steps.append((int(Step.STOCK_PREDICTION), "stock", stock))
        return steps

    async def _propose(self, doc: dict) -> None:
        task_id = bytes.fromhex(doc["task_id"][2:])
        task = await self.client.task(task_id)
        if task["outcome"] != Outcome.OPEN:
            # Sent before a restart; the event reader records the result.
            return await self._finish(doc, "submitted")
        pending = doc.get("pending_tx")
        if pending and pending["action"] == "propose":
            await self._transact(doc, "propose", None)
            return await self._finish(doc, "submitted")

        fund = self.client.config.contracts[doc["fund"]]
        position = await self.client.vault_position(doc["vault"], fund)
        request = AdvisorRequest(
            task_id=task_id,
            vault=doc["vault"],
            fund=fund,
            fund_label=doc["fund"],
            is_equity=position["is_equity"],
            price=position["price"],
            cash=position["cash"],
            units=position["units"],
            max_slippage_bps=position["max_slippage_bps"],
            evidence=tuple(
                _evidence_from_record(task_id, e) for e in doc.get("evidence", []) if "message" in e
            ),
        )
        decision = await self.advisor.decide(request)
        if decision is None:
            return await self._finish(doc, "no_trade")
        deadline = await self.client.now() + APPROVAL_SECONDS
        draft = build_proposal(
            request,
            decision,
            self.advisor,
            task["evidence_hash"],
            proposal_nonce(task_id),
            deadline,
        )
        signed = self.client.signer("advisor").sign_proposal(draft.proposal)
        record = draft.record | {
            "side": decision.side.name,
            "amount": str(decision.amount),
            "minimum_received": str(draft.proposal.minimumReceived),
            "confidence": decision.confidence,
            "deadline": deadline,
        }
        await self._transact(
            doc, "propose", self.client.proposal_call(signed), {"proposal": record}
        )
        await self._finish(doc, "submitted")

    # --- Transactions that survive a restart ---

    async def _transact(self, doc: dict, action: str, call, save_with: dict | None = None) -> dict:
        pending = doc.get("pending_tx")
        if pending and pending["action"] == action:
            receipt = await self.client.receipt(pending["hash"])
            if receipt is None and await self.client.mined_nonce() > pending["nonce"]:
                # Its nonce was used by another transaction, so it can never be mined.
                await self._save(doc, {"pending_tx": None})
                pending = None
            elif receipt is None:
                await self.client.broadcast(bytes.fromhex(pending["raw"]))
                receipt = await self.client.wait(pending["hash"])
            if pending:
                await self._save(doc, {"pending_tx": None})
                if receipt["status"] != 1:
                    raise ChainError(f"{action} transaction reverted")
                return receipt
        if call is None:
            raise ChainError(f"{action} was lost before it was sent; retrying")
        tx_hash, raw, nonce = await self.client.sign_tx(call)
        pending = {"action": action, "hash": tx_hash, "raw": raw.hex(), "nonce": nonce}
        await self._save(doc, {"pending_tx": pending} | (save_with or {}))
        await self.client.broadcast(raw)
        receipt = await self.client.wait(tx_hash)
        await self._save(doc, {"pending_tx": None})
        return receipt


def _evidence_record(result: EvidenceResult) -> dict:
    e = result.evidence
    message = {k: ("0x" + v.hex() if isinstance(v, bytes) else v) for k, v in e.message().items()}
    return {
        "step": e.step,
        "status": e.status,
        "score": e.score,
        "inputs": result.inputs,
        "outputs": result.outputs,
        "message": message,
        "struct_hash": "0x" + hashing.struct_hash("Evidence", e.message()).hex(),
    }


def _evidence_from_record(task_id: bytes, record: dict) -> EvidenceResult:
    m = record["message"]
    values = {
        k: (bytes.fromhex(v[2:]) if isinstance(v, str) and v.startswith("0x") else v)
        for k, v in m.items()
    }
    values["taskId"] = task_id
    return EvidenceResult(Evidence(**values), record.get("inputs", {}), record.get("outputs", {}))
