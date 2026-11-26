"""The one place that talks to the chain (Phase 10, B10).

The relayer pays gas for every transaction here; the sentiment, stock and
advisor keys only sign. The background worker (B12) adds retries and
restart safety on top; this client waits for each receipt and raises on a
revert, so HTTP requests must not call it directly.
"""

import json
from functools import cache
from pathlib import Path

from eth_utils import to_checksum_address
from web3 import AsyncHTTPProvider, AsyncWeb3
from web3.contract import AsyncContract

from app.services.blockchain.config import REPO_ROOT, BlockchainConfig
from app.services.blockchain.formats import Outcome, Reason
from app.services.blockchain.signing import RoleSigner, Signed

ARTIFACTS_DIR = REPO_ROOT / "blockchain" / "artifacts" / "contracts"
GAS_MARGIN_PERCENT = 25
RECEIPT_TIMEOUT_SECONDS = 120

# deployment name -> contract (ABI) name
_ABI_NAMES = {
    "tINR": "TestToken",
    "tEquityFund": "TestToken",
    "tDebtFund": "TestToken",
    "tGoldFund": "TestToken",
}


class ChainError(RuntimeError):
    pass


@cache
def load_abi(contract: str, artifacts_dir: Path = ARTIFACTS_DIR) -> list:
    matches = list(artifacts_dir.rglob(f"{contract}.json"))
    if not matches:
        raise ChainError(
            f"No ABI for {contract} in {artifacts_dir}; run `npm run compile` in blockchain/"
        )
    return json.loads(matches[0].read_text(encoding="utf-8"))["abi"]


class ChainClient:
    def __init__(self, config: BlockchainConfig, web3: AsyncWeb3 | None = None) -> None:
        self.config = config
        self.w3 = web3 or AsyncWeb3(AsyncHTTPProvider(config.rpc_url))
        self._relayer = config.accounts["relayer"]
        self._contracts: dict[str, AsyncContract] = {}

    def __repr__(self) -> str:  # the RPC URL may hold an API key
        return f"ChainClient(chain={self.config.chain_id})"

    # --- Contracts and signers ---

    def contract(self, name: str) -> AsyncContract:
        """A deployed contract by its deployment name, e.g. "AITaskManager"."""
        if name not in self._contracts:
            self._contracts[name] = self.w3.eth.contract(
                address=self.config.contracts[name], abi=load_abi(_ABI_NAMES.get(name, name))
            )
        return self._contracts[name]

    def at(self, abi_name: str, address: str) -> AsyncContract:
        return self.w3.eth.contract(address=to_checksum_address(address), abi=load_abi(abi_name))

    def vault(self, address: str) -> AsyncContract:
        return self.at("InvestmentVault", address)

    def signer(self, role: str) -> RoleSigner:
        if role not in ("sentiment", "stock", "advisor"):
            raise ValueError(f"{role} is not a signing role")
        return RoleSigner(
            self.config.accounts[role], self.config.chain_id, self.config.contracts["AITaskManager"]
        )

    async def check_network(self) -> None:
        """Raises if the RPC is for a different chain than the settings."""
        actual = await self.w3.eth.chain_id
        if actual != self.config.chain_id:
            raise ChainError(f"RPC is chain {actual}, settings say {self.config.chain_id}")

    async def now(self) -> int:
        """Latest block time; deadlines must use chain time, not the server clock."""
        return (await self.w3.eth.get_block("latest"))["timestamp"]

    # --- AITaskManager ---

    async def open_task(self, vault: str, fund: str, deadline: int) -> bytes:
        manager = self.contract("AITaskManager")
        receipt = await self.send(manager.functions.openTask(vault, fund, deadline))
        events = manager.events.TaskOpened().process_receipt(receipt)
        if not events:
            raise ChainError("openTask emitted no TaskOpened event")
        return bytes(events[0]["args"]["taskId"])

    async def submit_evidence(self, signed: Signed) -> dict:
        evidence = signed.message.message()
        call = self.contract("AITaskManager").functions.submitEvidence(evidence, signed.signature)
        return await self.send(call)

    async def submit_proposal(self, signed: Signed) -> dict:
        proposal = signed.message.message()
        call = self.contract("AITaskManager").functions.submitProposal(proposal, signed.signature)
        return await self.send(call)

    async def task(self, task_id: bytes) -> dict:
        vault, fund, deadline, outcome, reason, evidence_hash = (
            await self.contract("AITaskManager").functions.tasks(task_id).call()
        )
        return {
            "vault": vault,
            "fund": fund,
            "deadline": deadline,
            "outcome": Outcome(outcome),
            "reason": Reason(reason),
            "evidence_hash": bytes(evidence_hash),
        }

    # --- Vault state for the advisor ---

    async def vault_position(self, vault: str, fund: str) -> dict:
        """Cash, units, price and limits an advisor needs. Read-only."""
        token = self.at("TestToken", fund)
        cash = await self.contract("tINR").functions.balanceOf(vault).call()
        units = await token.functions.balanceOf(vault).call()
        price, price_time = await self.contract("MockPriceFeed").functions.price(fund).call()
        is_equity = await self.contract("MockFundMarket").functions.isEquity(fund).call()
        mandate = await self.contract("MandateManager").functions.mandateOf(vault).call()
        return {
            "cash": cash,
            "units": units,
            "price": price,
            "price_time": price_time,
            "is_equity": is_equity,
            "max_slippage_bps": mandate[7],  # Mandate.maxSlippageBps
        }

    # --- Transactions ---

    async def send(self, call) -> dict:
        """Sends `call` from the relayer and waits for it. Raises on revert."""
        sender = self._relayer.address
        tx = await call.build_transaction(
            {
                "from": sender,
                "nonce": await self.w3.eth.get_transaction_count(sender, "pending"),
                "chainId": self.config.chain_id,
            }
        )
        tx["gas"] = tx["gas"] * (100 + GAS_MARGIN_PERCENT) // 100
        signed = self._relayer.sign_transaction(tx)
        tx_hash = await self.w3.eth.send_raw_transaction(signed.raw_transaction)
        receipt = await self.w3.eth.wait_for_transaction_receipt(
            tx_hash, timeout=RECEIPT_TIMEOUT_SECONDS
        )
        if receipt["status"] != 1:
            raise ChainError(f"Transaction {tx_hash.hex()} reverted")
        return receipt
