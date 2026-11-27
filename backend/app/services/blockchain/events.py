"""Event reader: copies AITaskManager events into MongoDB (Phase 10, B12).

The only writer of task outcomes, so pending / executed / rejected always
match the chain, including approvals and declines sent from the wallet.

- Reads only blocks with enough confirmations (BLOCKCHAIN_CONFIRMATIONS).
- Saves the hash of the last block read. If that block is no longer on the
  chain (a reorganization), it drops what it stored from the last
  REORG_WINDOW blocks, resets those task outcomes and reads them again.
- Each log is stored once (unique tx hash + log index), so rescans are safe.
"""

import logging
from collections.abc import Mapping
from datetime import UTC, datetime

from app.core.config import settings
from app.data import blockchain_repository as repo
from app.data.collections import get_chain_tasks_collection
from app.services.blockchain.client import ChainClient
from app.services.blockchain.formats import Outcome, Reason

logger = logging.getLogger(__name__)

CURSOR = "event_cursor"
CHUNK_BLOCKS = 2000
REORG_WINDOW = 64
EVENTS = ("TaskOpened", "EvidenceSubmitted", "ProposalSubmitted", "TaskResult")
OUTCOME_STATES = {
    Outcome.PENDING_USER: "pending_user",
    Outcome.EXECUTED: "executed",
    Outcome.REJECTED: "rejected",
}


async def sync_events(client: ChainClient) -> int:
    """Reads new events; returns how many it stored."""
    w3 = client.w3
    head = await w3.eth.block_number - settings.blockchain_confirmations
    cursor = await repo.get_state(CURSOR)
    start = settings.blockchain_start_block
    if cursor:
        start = cursor["block"] + 1
        if cursor["block"] >= 0 and await _block_hash(w3, cursor["block"]) != cursor["hash"]:
            start = max(settings.blockchain_start_block, cursor["block"] - REORG_WINDOW + 1)
            await _roll_back(start)
            # Point the cursor at a block that is still there.
            previous = start - 1
            hash_ = await _block_hash(w3, previous) if previous >= 0 else None
            await repo.set_state(CURSOR, {"block": previous, "hash": hash_})
    if head < start:
        return 0

    stored = 0
    manager = client.contract("AITaskManager")
    for low in range(start, head + 1, CHUNK_BLOCKS):
        high = min(low + CHUNK_BLOCKS - 1, head)
        logs = []
        for name in EVENTS:
            logs += await getattr(manager.events, name)().get_logs(from_block=low, to_block=high)
        for log in sorted(logs, key=lambda e: (e["blockNumber"], e["logIndex"])):
            if await repo.insert_event(_event_doc(log)):
                stored += 1
                await _apply(log)
        await repo.set_state(CURSOR, {"block": high, "hash": await _block_hash(w3, high)})
    return stored


async def _block_hash(w3, number: int) -> str | None:
    from web3.exceptions import BlockNotFound

    try:
        block = await w3.eth.get_block(number)
    except BlockNotFound:  # the chain is now shorter than our cursor
        return None
    return "0x" + bytes(block["hash"]).hex()


async def _roll_back(from_block: int) -> None:
    dropped = await repo.delete_events_from(from_block)
    result = await get_chain_tasks_collection().update_many(
        {"outcome_block": {"$gte": from_block}},
        {
            "$set": {
                "state": "submitted",
                "outcome": None,
                "reason": None,
                "amount_out": None,
                "outcome_block": None,
                "updated_at": datetime.now(UTC),
            }
        },
    )
    logger.warning(
        "Chain reorganization: re-reading from block %d (%d events, %d tasks reset)",
        from_block,
        dropped,
        result.modified_count,
    )


def _event_doc(log) -> dict:
    return {
        "event": log["event"],
        "block_number": log["blockNumber"],
        "block_hash": "0x" + bytes(log["blockHash"]).hex(),
        "tx_hash": "0x" + bytes(log["transactionHash"]).hex(),
        "log_index": log["logIndex"],
        "task_id": "0x" + bytes(log["args"]["taskId"]).hex(),
        "args": _plain(dict(log["args"])),
        "stored_at": datetime.now(UTC),
    }


async def _apply(log) -> None:
    if log["event"] != "TaskResult":
        return
    outcome = Outcome(log["args"]["outcome"])
    task_id = "0x" + bytes(log["args"]["taskId"]).hex()
    fields = {
        "outcome": outcome.name,
        "reason": Reason(log["args"]["reason"]).name,
        "amount_out": str(log["args"]["amountOut"]),
        "outcome_block": log["blockNumber"],
        "updated_at": datetime.now(UTC),
    }
    if outcome in OUTCOME_STATES:
        fields["state"] = OUTCOME_STATES[outcome]
    # Older events never overwrite a newer outcome.
    await get_chain_tasks_collection().update_one(
        {
            "task_id": task_id,
            "$or": [{"outcome_block": None}, {"outcome_block": {"$lte": log["blockNumber"]}}],
        },
        {"$set": fields},
    )


def _plain(value):
    """Event args as MongoDB-safe values: bytes to hex, big ints to strings."""
    if isinstance(value, bytes):
        return "0x" + value.hex()
    if isinstance(value, Mapping):
        return {k: _plain(v) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [_plain(v) for v in value]
    if isinstance(value, int) and not isinstance(value, bool) and abs(value) >= 2**63:
        return str(value)
    return value
