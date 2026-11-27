"""Print the backend/.env lines for a local blockchain demo (Phase 10).

    python -m scripts.local_chain_env

Uses Hardhat's published test accounts 2-6, one per role. Their keys are
public, which is fine on the local chain only; the app refuses them on any
other network. Account 0 deploys and registers models, and account 1 is the
one to import into MetaMask as the vault owner.
"""

import json
import sys

from eth_account import Account

from app.services.blockchain.config import REPO_ROOT

MNEMONIC = "test test test test test test test test test test test junk"  # Hardhat's public words
ROLES = ("SENTIMENT", "STOCK", "ADVISOR", "RELAYER", "SIP_RUNNER")


def main() -> None:
    deployment = REPO_ROOT / "blockchain" / "deployments" / "local.json"
    if not deployment.exists():
        sys.exit("Run `npm run node` and `npm run deploy:local` in blockchain/ first")
    metrics = json.loads(
        (REPO_ROOT / "ml" / "models" / "stock_predictor" / "metrics.json").read_text(encoding="utf-8")
    )
    Account.enable_unaudited_hdwallet_features()
    print("BLOCKCHAIN_ENABLED=true")
    print("BLOCKCHAIN_RPC_URL=http://127.0.0.1:8545")
    print("BLOCKCHAIN_CHAIN_ID=31337")
    print("BLOCKCHAIN_DEPLOYMENT_PATH=blockchain/deployments/local.json")
    for i, role in enumerate(ROLES, start=2):
        account = Account.from_mnemonic(MNEMONIC, account_path=f"m/44'/60'/0'/0/{i}")
        print(f"BLOCKCHAIN_{role}_PRIVATE_KEY={account.key.hex()}")
    print("BLOCKCHAIN_SENTIMENT_MODEL_VERSION=1")
    print(f"BLOCKCHAIN_STOCK_MODEL_VERSION={metrics['model_version']}")
    owner = Account.from_mnemonic(MNEMONIC, account_path="m/44'/60'/0'/0/1")
    print(f"\n# MetaMask: add network http://127.0.0.1:8545 (chain 31337) and import {owner.address}")
    print(f"# with its public Hardhat key {owner.key.hex()}")


if __name__ == "__main__":
    main()
