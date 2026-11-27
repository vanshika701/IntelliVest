"""End to end on a local Hardhat chain (Phase 10, B10).

Opens a task, submits stock evidence built from a Phase 4 prediction record
and sentiment evidence, gets a mock-advisor proposal, and checks that the
vault executes it. Skipped unless a local chain is running and deployed:

    cd blockchain && npm run node            # keep open
    cd blockchain && npm run deploy:local    # second terminal
    set BLOCKCHAIN_TEST_RPC=http://127.0.0.1:8545 and run pytest
"""

import json
import os
import uuid
from datetime import UTC, datetime

import pytest
from eth_account import Account

from app.services.blockchain import hashing
from app.services.blockchain.config import REPO_ROOT, REQUIRED_CONTRACTS, BlockchainConfig
from app.services.blockchain.formats import (
    Evidence,
    EvidenceResult,
    EvidenceStatus,
    Outcome,
    Reason,
    Side,
    Step,
)

RPC = os.environ.get("BLOCKCHAIN_TEST_RPC")
DEPLOYMENT = REPO_ROOT / "blockchain" / "deployments" / "local.json"
pytestmark = pytest.mark.skipif(
    not RPC or not DEPLOYMENT.exists(), reason="needs BLOCKCHAIN_TEST_RPC and a local deployment"
)

U = 1_000_000
MNEMONIC = (
    "test test test test test test test test test test test junk"  # Hardhat's public test words
)
ROLES = ("sentiment", "stock", "advisor", "relayer", "sip_runner")


def _hardhat(i: int):
    Account.enable_unaudited_hdwallet_features()
    return Account.from_mnemonic(MNEMONIC, account_path=f"m/44'/60'/0'/0/{i}")


async def _send_as(w3, account, call):
    tx = await call.build_transaction(
        {
            "from": account.address,
            "nonce": await w3.eth.get_transaction_count(account.address, "pending"),
        }
    )
    tx_hash = await w3.eth.send_raw_transaction(account.sign_transaction(tx).raw_transaction)
    receipt = await w3.eth.wait_for_transaction_receipt(tx_hash)
    assert receipt["status"] == 1
    return receipt


@pytest.fixture
def client():
    from app.services.blockchain.client import ChainClient

    contracts = json.loads(DEPLOYMENT.read_text(encoding="utf-8"))["contracts"]
    config = BlockchainConfig(
        rpc_url=RPC,
        chain_id=31337,
        contracts={name: contracts[name] for name in REQUIRED_CONTRACTS},
        accounts={role: _hardhat(2 + i) for i, role in enumerate(ROLES)},
    )
    return ChainClient(config)


async def test_mock_advisor_trade_executes_with_stock_evidence(client):
    from app.services.blockchain.advisor import AdvisorRequest, build_proposal, proposal_nonce
    from app.services.blockchain.mock_advisor import MockAdvisor
    from app.services.blockchain.stock_evidence import build_stock_evidence, model_ref

    await client.check_network()
    w3, admin, user = client.w3, _hardhat(0), _hardhat(1)
    c = client.contract
    fund = client.config.contracts["tEquityFund"]
    run = uuid.uuid4().hex[:8]  # fresh versions, so the test can rerun on one chain
    advisor = MockAdvisor()
    advisor.model_version = f"test-{run}"
    record = {
        "ticker": "RELIANCE",
        "as_of": datetime.fromtimestamp(await client.now(), UTC).replace(
            hour=0, minute=0, second=0
        ),
        "horizon_days": 5,
        "chance_beat": 0.71,
        "target": "excess_log_return_vs_nifty",
        "model_version": f"stock-{run}",
        "artifact_hash": hashing.keccak(text=run).hex(),
    }
    sentiment = (hashing.model_id("ProsusAI/finbert"), hashing.model_id(f"sent-{run}"))
    stock_id, stock_version, artifact = model_ref(record)
    advisor_ref = (hashing.model_id(advisor.model_name), hashing.model_id(advisor.model_version))

    # Admin registers the three versions; each signs with its own key.
    registry = c("ModelRegistry")
    for (mid, ver), step, role, art in (
        (sentiment, Step.SENTIMENT, "sentiment", bytes(32)),
        ((stock_id, stock_version), Step.STOCK_PREDICTION, "stock", artifact),
        (advisor_ref, Step.ADVISOR, "advisor", bytes(32)),
    ):
        signer = client.config.accounts[role].address
        await _send_as(w3, admin, registry.functions.register(mid, ver, int(step), signer, art))
    # Keep the price fresh on a long-running chain.
    feed = c("MockPriceFeed")
    price, updated = await feed.functions.price(fund).call()
    if await client.now() - updated > 3600:
        await _send_as(w3, admin, feed.functions.setPrice(fund, price))

    # The user: vault, deposit, mandate accepting these versions.
    factory = c("VaultFactory")
    vault = await factory.functions.vaultOf(user.address).call()
    if int(vault, 16) == 0:
        await _send_as(w3, user, factory.functions.createVault())
        vault = await factory.functions.vaultOf(user.address).call()
    inr = c("tINR")
    await _send_as(w3, user, inr.functions.faucet(10_000 * U))
    await _send_as(w3, user, inr.functions.approve(vault, 10_000 * U))
    await _send_as(w3, user, client.vault(vault).functions.deposit(10_000 * U))
    now = await client.now()
    mandate = (
        # caps stay above the trade size when reruns grow the vault
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
        True,
        True,
        True,
    )
    keys = [hashing.model_key(*m) for m in (sentiment, (stock_id, stock_version), advisor_ref)]
    await _send_as(w3, user, c("MandateManager").functions.setMandate(vault, mandate, [fund], keys))

    # Task -> evidence -> proposal, all sent by the relayer.
    task_id = await client.open_task(vault, fund, now + 3600)
    stock = build_stock_evidence(
        task_id, "RELIANCE", 5, [record], datetime.now(UTC), record["model_version"]
    )
    assert stock.evidence.status == EvidenceStatus.OK
    sent = Evidence(
        task_id,
        int(Step.SENTIMENT),
        int(EvidenceStatus.OK),
        *sentiment,
        hashing.hash_data({"articles": []}),
        hashing.hash_data({"score": 3000}),
        3000,
        6,
        0,
        now - 60,
    )
    chained = hashing.ZERO_HASH
    for result, role in ((EvidenceResult(sent, {}, {}), "sentiment"), (stock, "stock")):
        await client.submit_evidence(client.signer(role).sign_evidence(result.evidence))
        chained = hashing.chain_evidence(
            chained, hashing.struct_hash("Evidence", result.evidence.message())
        )
    task = await client.task(task_id)
    assert task["evidence_hash"] == chained and task["outcome"] == Outcome.OPEN

    position = await client.vault_position(vault, fund)
    request = AdvisorRequest(
        task_id=task_id,
        vault=vault,
        fund=fund,
        fund_label="tEquityFund",
        is_equity=position["is_equity"],
        price=position["price"],
        cash=position["cash"],
        units=position["units"],
        max_slippage_bps=position["max_slippage_bps"],
        evidence=(EvidenceResult(sent, {}, {}), stock),
    )
    decision = await advisor.decide(request)
    assert decision.side == Side.BUY
    draft = build_proposal(
        request, decision, advisor, task["evidence_hash"], proposal_nonce(task_id), now + 1800
    )
    await client.submit_proposal(client.signer("advisor").sign_proposal(draft.proposal))

    task = await client.task(task_id)
    assert (task["outcome"], task["reason"]) == (Outcome.EXECUTED, Reason.NONE)
    after = await client.vault_position(vault, fund)
    assert after["cash"] == position["cash"] - decision.amount
    assert after["units"] >= position["units"] + draft.proposal.minimumReceived


async def test_wrong_role_key_is_refused(client):
    from app.services.blockchain.client import ChainError

    vault = client.config.contracts["tINR"]  # any address; the signature check fails first
    task_id = await client.open_task(
        vault, client.config.contracts["tEquityFund"], await client.now() + 600
    )
    e = Evidence(
        task_id,
        int(Step.STOCK_PREDICTION),
        0,
        hashing.model_id("nope"),
        hashing.model_id("1"),
        bytes(32),
        bytes(32),
        6000,
        0,
        1,
        await client.now(),
    )
    with pytest.raises(Exception) as info:  # the estimate reverts before sending
        await client.submit_evidence(client.signer("advisor").sign_evidence(e))
    assert "model not active" in str(info.value) or isinstance(info.value, ChainError)
