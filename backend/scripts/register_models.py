"""Register model versions and their signers in ModelRegistry (Phase 10).

    python -m scripts.register_models [--stock-version 1.0.0] [--sentiment-version ...]

Needs BLOCKCHAIN_ENABLED=true and the role keys in backend/.env. The
registry admin key is BLOCKCHAIN_ADMIN_PRIVATE_KEY, read from the
environment for this script only; on the local chain it defaults to
Hardhat's public account 0 (the deployer). Already registered versions are
skipped. Each vault owner must still accept a new version in their mandate.

Prints the BLOCKCHAIN_*_MODEL_VERSION lines to put in backend/.env.
"""

import argparse
import asyncio
import hashlib
import json
import os
from pathlib import Path

from eth_account import Account

from app.core.config import settings
from app.services.blockchain import hashing
from app.services.blockchain.client import ChainClient
from app.services.blockchain.config import LOCAL_CHAIN_ID, REPO_ROOT, load_blockchain_config
from app.services.blockchain.formats import Step
from app.services.blockchain.mock_advisor import MockAdvisor
from app.services.blockchain.stock_evidence import MODEL_NAME as STOCK_MODEL

HARDHAT_DEPLOYER_KEY = (
    "0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80"  # public
)


def stock_model() -> tuple[str, bytes]:
    """(version, sha256 of the model file), as Phase 4 stores them."""
    path = Path(settings.stock_predictor_path)
    path = path if path.is_absolute() else REPO_ROOT / path
    metrics = json.loads(path.with_name("metrics.json").read_text(encoding="utf-8"))
    return metrics["model_version"], hashlib.sha256(path.read_bytes()).digest()


async def register(
    client: ChainClient, admin, name: str, version: str, step: Step, role: str, artifact: bytes
) -> None:
    registry = client.contract("ModelRegistry")
    model_id, version_id = hashing.model_id(name), hashing.model_id(version)
    existing = await registry.functions.get(hashing.model_key(model_id, version_id)).call()
    if int(existing[0], 16) != 0:
        print(f"already registered: {name} {version}")
        return
    signer = client.config.accounts[role].address
    call = registry.functions.register(model_id, version_id, int(step), signer, artifact)
    tx = await call.build_transaction(
        {
            "from": admin.address,
            "nonce": await client.w3.eth.get_transaction_count(admin.address, "pending"),
        }
    )
    tx_hash = await client.w3.eth.send_raw_transaction(admin.sign_transaction(tx).raw_transaction)
    receipt = await client.w3.eth.wait_for_transaction_receipt(tx_hash)
    if receipt["status"] != 1:
        raise SystemExit(f"registering {name} {version} reverted")
    print(f"registered: {name} {version} -> {role} signer {signer}")


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--stock-version", help="default: the trained model's metrics.json")
    parser.add_argument("--sentiment-version", default="1")
    args = parser.parse_args()

    config = load_blockchain_config(settings)
    if config is None:
        raise SystemExit("Set BLOCKCHAIN_ENABLED=true first")
    key = os.environ.get("BLOCKCHAIN_ADMIN_PRIVATE_KEY")
    if not key:
        if config.chain_id != LOCAL_CHAIN_ID:
            raise SystemExit("Set BLOCKCHAIN_ADMIN_PRIVATE_KEY in the environment")
        key = HARDHAT_DEPLOYER_KEY
    admin = Account.from_key(key)
    client = ChainClient(config)
    await client.check_network()

    stock_version, artifact = stock_model()
    stock_version = args.stock_version or stock_version
    advisor = MockAdvisor()
    await register(
        client,
        admin,
        settings.sentiment_model,
        args.sentiment_version,
        Step.SENTIMENT,
        "sentiment",
        bytes(32),
    )
    await register(
        client, admin, STOCK_MODEL, stock_version, Step.STOCK_PREDICTION, "stock", artifact
    )
    await register(
        client, admin, advisor.model_name, advisor.model_version, Step.ADVISOR, "advisor", bytes(32)
    )
    print(f"\nBLOCKCHAIN_SENTIMENT_MODEL_VERSION={args.sentiment_version}")
    print(f"BLOCKCHAIN_STOCK_MODEL_VERSION={stock_version}")


if __name__ == "__main__":
    asyncio.run(main())
