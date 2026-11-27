"""Worker retries, leases and error hiding, without a chain (Phase 10, B12)."""

from datetime import UTC, datetime, timedelta

from app.data import blockchain_repository as repo
from app.data.collections import get_chain_tasks_collection
from app.services.blockchain.worker import MAX_ATTEMPTS, Worker, backoff, safe_error

RPC = "https://rpc.example/v3/secret-key"


class FakeConfig:
    rpc_url = RPC


class FakeClient:
    config = FakeConfig()


class Broken(Worker):
    async def advance(self, doc):
        raise ConnectionError(f"could not reach {RPC}")


async def _queued(**over) -> dict:
    now = datetime.now(UTC)
    doc = {
        "user_id": "u",
        "fund": "tEquityFund",
        "wallet": "0x" + "1" * 40,
        "state": "queued",
        "active": True,
        "attempts": 0,
        "next_attempt_at": now - timedelta(seconds=1),
        "lease_until": None,
        "created_at": now,
        "updated_at": now,
    } | over
    await repo.insert_task(doc)
    return doc


def test_backoff_grows_and_caps():
    assert [backoff(n).total_seconds() for n in (1, 2, 3)] == [15, 30, 60]
    assert backoff(20) == timedelta(minutes=10)


def test_safe_error_hides_rpc_url():
    text = safe_error(ConnectionError(f"failed {RPC}"), RPC)
    assert "secret-key" not in text and "<rpc>" in text and text.startswith("ConnectionError")


async def test_failure_is_retried_later_then_given_up(mongo_test_db):
    await _queued()
    worker = Broken(FakeClient())
    assert await worker.run_due() == 1
    doc = await get_chain_tasks_collection().find_one({})
    assert doc["attempts"] == 1 and doc["active"] is True and doc["lease_until"] is None
    assert "secret-key" not in doc["last_error"]
    # Not due yet, so nothing runs.
    assert await worker.run_due() == 0

    await get_chain_tasks_collection().update_one(
        {}, {"$set": {"attempts": MAX_ATTEMPTS - 1, "next_attempt_at": datetime.now(UTC)}}
    )
    await worker.run_due()
    doc = await get_chain_tasks_collection().find_one({})
    assert (doc["state"], doc["active"]) == ("failed", False)


async def test_leased_task_is_not_taken_twice(mongo_test_db):
    await _queued(lease_until=datetime.now(UTC) + timedelta(minutes=5))
    assert await Broken(FakeClient()).run_due() == 0


async def test_expired_lease_is_taken(mongo_test_db):
    await _queued(lease_until=datetime.now(UTC) - timedelta(minutes=1))
    assert await Broken(FakeClient()).run_due() == 1
