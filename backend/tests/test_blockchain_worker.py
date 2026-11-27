"""Worker and event reader on a local Hardhat chain plus MongoDB (Phase 10, B12).

Skipped unless BLOCKCHAIN_TEST_RPC points at a running, deployed local chain
(see test_blockchain_chain.py). Each test uses a fresh user and vault.
"""

import json
import os
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from eth_account import Account

from app.core.config import settings
from app.data import blockchain_repository as repo
from app.data.collections import get_chain_tasks_collection, get_stock_predictions_collection
from app.services.blockchain import hashing
from app.services.blockchain.config import REPO_ROOT, REQUIRED_CONTRACTS, BlockchainConfig
from app.services.blockchain.formats import Step

RPC = os.environ.get("BLOCKCHAIN_TEST_RPC")
DEPLOYMENT = REPO_ROOT / "blockchain" / "deployments" / "local.json"
pytestmark = pytest.mark.skipif(
    not RPC or not DEPLOYMENT.exists(), reason="needs BLOCKCHAIN_TEST_RPC and a local deployment"
)

U = 1_000_000
MNEMONIC = "test test test test test test test test test test test junk"  # Hardhat's public words
ROLES = ("sentiment", "stock", "advisor", "relayer", "sip_runner")


def _hardhat(i: int):
    Account.enable_unaudited_hdwallet_features()
    return Account.from_mnemonic(MNEMONIC, account_path=f"m/44'/60'/0'/0/{i}")


async def _send_as(w3, account, call=None, tx=None):
    tx = tx or await call.build_transaction({"from": account.address})
    tx["nonce"] = await w3.eth.get_transaction_count(account.address, "pending")
    tx.setdefault("chainId", 31337)
    if "gas" not in tx:
        tx["gas"] = 100_000
        tx["gasPrice"] = await w3.eth.gas_price
    tx_hash = await w3.eth.send_raw_transaction(account.sign_transaction(tx).raw_transaction)
    receipt = await w3.eth.wait_for_transaction_receipt(tx_hash)
    assert receipt["status"] == 1
    return receipt


class Chain:
    """One user with a vault and mandate, plus models registered for this test."""

    def __init__(self, client, user, vault, advisor, task_count) -> None:
        self.client, self.user, self.vault, self.advisor = client, user, vault, advisor
        self.task_count = task_count

    async def opened(self) -> int:
        count = await self.client.contract("AITaskManager").functions.taskCount().call()
        return count - self.task_count


async def _setup(monkeypatch, *, vault=True, require_stock=True, sentiment=False) -> Chain:
    from app.services.blockchain.client import ChainClient
    from app.services.blockchain.mock_advisor import MockAdvisor
    from app.services.blockchain.stock_evidence import MODEL_NAME

    contracts = json.loads(DEPLOYMENT.read_text(encoding="utf-8"))["contracts"]
    config = BlockchainConfig(
        rpc_url=RPC,
        chain_id=31337,
        contracts={n: contracts[n] for n in REQUIRED_CONTRACTS},
        accounts={role: _hardhat(2 + i) for i, role in enumerate(ROLES)},
    )
    client = ChainClient(config)
    w3, c, admin = client.w3, client.contract, _hardhat(0)
    run = uuid.uuid4().hex[:8]
    stock_version = f"stock-{run}"
    monkeypatch.setattr(settings, "blockchain_stock_model_version", stock_version)
    advisor = MockAdvisor()
    advisor.model_version = f"adv-{run}"
    stock = (hashing.model_id(MODEL_NAME), hashing.model_id(stock_version))
    adv = (hashing.model_id(advisor.model_name), hashing.model_id(advisor.model_version))
    models = [(stock, Step.STOCK_PREDICTION, "stock"), (adv, Step.ADVISOR, "advisor")]
    sent = (hashing.model_id(settings.sentiment_model), hashing.model_id(f"sent-{run}"))
    if sentiment:
        monkeypatch.setattr(settings, "blockchain_sentiment_model_version", f"sent-{run}")
        models.append((sent, Step.SENTIMENT, "sentiment"))
    else:
        monkeypatch.setattr(settings, "blockchain_sentiment_model_version", None)
    registry = c("ModelRegistry")
    for (mid, ver), step, role in models:
        signer = config.accounts[role].address
        await _send_as(
            w3, admin, registry.functions.register(mid, ver, int(step), signer, bytes(32))
        )
    fund = contracts["tEquityFund"]
    price, updated = await c("MockPriceFeed").functions.price(fund).call()
    if await client.now() - updated > 3600:
        await _send_as(w3, admin, c("MockPriceFeed").functions.setPrice(fund, price))

    user = Account.create()
    await _send_as(w3, admin, tx={"to": user.address, "value": 10**18})
    vault_addr = None
    if vault:
        await _send_as(w3, user, c("VaultFactory").functions.createVault())
        vault_addr = await c("VaultFactory").functions.vaultOf(user.address).call()
        await _send_as(w3, user, c("tINR").functions.faucet(10_000 * U))
        await _send_as(w3, user, c("tINR").functions.approve(vault_addr, 10_000 * U))
        await _send_as(w3, user, client.vault(vault_addr).functions.deposit(10_000 * U))
        now = await client.now()
        mandate = (
            now - 60,
            now + 86400,
            10**6 * U,
            10**7 * U,
            10**8 * U,
            10**6 * U,
            10_000,
            100,
            5000,
            50,
            5000,
            sentiment,
            require_stock,
            True,
        )
        keys = [hashing.model_key(*m) for m, _, _ in models]
        await _send_as(
            w3, user, c("MandateManager").functions.setMandate(vault_addr, mandate, [fund], keys)
        )

    # A stored Phase 4 prediction for today.
    today = datetime.fromtimestamp(await client.now(), UTC).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    await get_stock_predictions_collection().insert_one(
        {
            "ticker": "RELIANCE",
            "as_of": today,
            "horizon_days": 5,
            "chance_up": 0.75,
            "model_version": stock_version,
            "artifact_hash": "cd" * 32,
        }
    )
    if sentiment:  # three FinBERT-scored headlines from today
        from app.data.collections import get_news_collection

        await get_news_collection().insert_many(
            [
                {
                    "url": f"https://news.example/{run}/{i}",
                    "title": f"Reliance headline {i}",
                    "tickers": ["RELIANCE"],
                    "published_at": datetime.fromtimestamp(await client.now(), UTC)
                    - timedelta(hours=i + 1),
                    "sentiment": {
                        "label": "positive",
                        "score": 0.4,
                        "model": settings.sentiment_model,
                    },
                }
                for i in range(3)
            ]
        )
    await repo.insert_wallet_link("user-" + run, user.address, datetime.now(UTC))
    task_count = await c("AITaskManager").functions.taskCount().call()
    chain = Chain(client, user, vault_addr, advisor, task_count)
    chain.user_id = "user-" + run
    return chain


async def _queue(chain: Chain, ticker: str | None = "RELIANCE") -> dict:
    from app.services.blockchain.task_service import create_task

    return await create_task(chain.user_id, "tEquityFund", ticker, 5)


async def _doc(task: dict) -> dict:
    from bson import ObjectId

    return await get_chain_tasks_collection().find_one({"_id": ObjectId(task["id"])})


async def _retry_now(task: dict) -> None:
    from bson import ObjectId

    await get_chain_tasks_collection().update_one(
        {"_id": ObjectId(task["id"])},
        {"$set": {"next_attempt_at": datetime.now(UTC) - timedelta(seconds=1)}},
    )


@pytest.fixture
async def events_from_now(mongo_test_db, monkeypatch):
    """The reader starts at the current block, not the chain's whole history."""
    from web3 import AsyncHTTPProvider, AsyncWeb3

    head = await AsyncWeb3(AsyncHTTPProvider(RPC)).eth.block_number
    monkeypatch.setattr(settings, "blockchain_start_block", head)
    return mongo_test_db


async def test_task_runs_end_to_end(events_from_now, monkeypatch):
    from app.services.blockchain.events import sync_events
    from app.services.blockchain.worker import Worker

    chain = await _setup(monkeypatch)
    task = await _queue(chain)
    assert await Worker(chain.client, chain.advisor).run_due() == 1
    doc = await _doc(task)
    assert doc["state"] == "submitted" and doc["active"] is False and doc["pending_tx"] is None
    assert [e["step"] for e in doc["evidence"]] == [Step.STOCK_PREDICTION]
    assert doc["evidence"][0]["outputs"]["chance_up_bps"] == 7500 and doc["evidence"][0]["tx_hash"]
    assert doc["proposal"]["side"] == "BUY" and "salt" in doc["proposal"]

    assert await sync_events(chain.client) >= 4  # opened, evidence, proposal, result
    doc = await _doc(task)
    assert (doc["state"], doc["outcome"], doc["reason"]) == ("executed", "EXECUTED", "NONE")
    assert int(doc["amount_out"]) > 0
    # Reading again stores nothing twice.
    assert await sync_events(chain.client) == 0
    assert await chain.opened() == 1


async def test_crash_before_sending_opens_one_task(events_from_now, monkeypatch):
    from app.services.blockchain.worker import Worker

    chain = await _setup(monkeypatch)
    task = await _queue(chain)
    real = chain.client.broadcast

    async def crash(raw):
        raise ConnectionError("down")

    monkeypatch.setattr(chain.client, "broadcast", crash)
    await Worker(chain.client, chain.advisor).run_due()
    doc = await _doc(task)
    assert (
        doc["state"] == "opening" and doc["pending_tx"]["action"] == "open" and doc["attempts"] == 1
    )
    assert await chain.opened() == 0

    monkeypatch.setattr(chain.client, "broadcast", real)
    await _retry_now(task)
    await Worker(chain.client, chain.advisor).run_due()
    assert (await _doc(task))["state"] == "submitted"
    assert await chain.opened() == 1


async def test_crash_after_sending_does_not_resend(events_from_now, monkeypatch):
    from app.services.blockchain.client import ChainError
    from app.services.blockchain.worker import Worker

    chain = await _setup(monkeypatch)
    task = await _queue(chain)
    real = chain.client.wait
    calls = {"n": 0}

    async def lose_first_receipt(tx_hash):
        calls["n"] += 1
        if calls["n"] == 1:
            raise ChainError("timed out")
        return await real(tx_hash)

    monkeypatch.setattr(chain.client, "wait", lose_first_receipt)
    await Worker(chain.client, chain.advisor).run_due()
    assert (await _doc(task))["pending_tx"]["action"] == "open"
    await _retry_now(task)
    await Worker(chain.client, chain.advisor).run_due()
    assert (await _doc(task))["state"] == "submitted"
    assert await chain.opened() == 1


async def test_no_vault_fails_without_chain_writes(events_from_now, monkeypatch):
    from app.services.blockchain.worker import Worker

    chain = await _setup(monkeypatch, vault=False)
    task = await _queue(chain)
    await Worker(chain.client, chain.advisor).run_due()
    doc = await _doc(task)
    assert (doc["state"], doc["last_error"]) == ("failed", "Create a vault first")
    assert await chain.opened() == 0


async def test_no_prediction_goes_to_the_owner(events_from_now, monkeypatch):
    from app.services.blockchain.events import sync_events
    from app.services.blockchain.mock_advisor import MockAdvisor
    from app.services.blockchain.worker import Worker

    class AlwaysBuy(MockAdvisor):
        async def decide(self, request):
            from app.services.blockchain.advisor import AdvisorDecision
            from app.services.blockchain.formats import Side

            return AdvisorDecision(Side.BUY, 100 * U, 9000, "test")

    chain = await _setup(monkeypatch)
    advisor = AlwaysBuy()
    advisor.model_version = chain.advisor.model_version
    task = await _queue(chain, ticker=None)  # no stock: evidence is NO_DATA
    await Worker(chain.client, advisor).run_due()
    assert (await _doc(task))["evidence"][0]["status"] == 1
    await sync_events(chain.client)
    doc = await _doc(task)
    assert (doc["state"], doc["outcome"]) == ("pending_user", "PENDING_USER")


async def test_reorganized_blocks_are_read_again(events_from_now, monkeypatch):
    from app.services.blockchain.events import sync_events
    from app.services.blockchain.worker import Worker

    chain = await _setup(monkeypatch)
    w3 = chain.client.w3
    snapshot = await w3.provider.make_request("evm_snapshot", [])
    task = await _queue(chain)
    await Worker(chain.client, chain.advisor).run_due()
    await sync_events(chain.client)
    assert (await _doc(task))["state"] == "executed"

    # Replace those blocks with empty ones, as a reorganization would.
    await w3.provider.make_request("evm_revert", [snapshot["result"]])
    for _ in range(8):
        await w3.provider.make_request("evm_mine", [])
    await sync_events(chain.client)
    doc = await _doc(task)
    assert (doc["state"], doc["outcome"]) == ("submitted", None)
    assert await repo.get_task_by_chain_id(doc["task_id"]) is not None
    from app.data.collections import get_chain_events_collection

    assert await get_chain_events_collection().count_documents({"task_id": doc["task_id"]}) == 0


async def test_sentiment_and_stock_evidence_both_count(events_from_now, monkeypatch):
    from app.services.blockchain.events import sync_events
    from app.services.blockchain.worker import Worker

    chain = await _setup(monkeypatch, sentiment=True)
    task = await _queue(chain)
    await Worker(chain.client, chain.advisor).run_due()
    doc = await _doc(task)
    assert [e["step"] for e in doc["evidence"]] == [Step.SENTIMENT, Step.STOCK_PREDICTION]
    assert doc["evidence"][0]["score"] == 4000 and doc["evidence"][0]["status"] == 0
    await sync_events(chain.client)
    assert (await _doc(task))["state"] == "executed"
