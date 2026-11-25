"""Validated blockchain configuration (Phase 10, B9).

Error messages name settings but never contain their values, so a key can't
end up in a log.
"""

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit

from eth_account import Account
from eth_account.signers.local import LocalAccount
from eth_utils import is_address, to_checksum_address

from app.core.config import Settings

REPO_ROOT = Path(__file__).resolve().parents[4]

LOCAL_CHAIN_ID = 31337
# Test networks only: Hardhat, Ethereum Sepolia, Polygon Amoy.
ALLOWED_CHAIN_IDS = frozenset({LOCAL_CHAIN_ID, 11155111, 80002})

REQUIRED_CONTRACTS = (
    "tINR",
    "tEquityFund",
    "tDebtFund",
    "tGoldFund",
    "MockPriceFeed",
    "MockFundMarket",
    "ModelRegistry",
    "MandateManager",
    "AITaskManager",
    "VaultFactory",
)

# The first three only sign. The relayer and SIP runner send transactions and
# pay gas.
ROLES = ("sentiment", "stock", "advisor", "relayer", "sip_runner")

# Published by Hardhat, so anyone can use the accounts these words create.
_HARDHAT_MNEMONIC = "test test test test test test test test test test test junk"

_PRIVATE_KEY = re.compile(r"(0x)?[0-9a-fA-F]{64}")


class BlockchainConfigError(ValueError):
    pass


@dataclass(frozen=True)
class BlockchainConfig:
    rpc_url: str = field(repr=False)  # often contains a provider API key
    chain_id: int
    contracts: dict[str, str]
    accounts: dict[str, LocalAccount] = field(repr=False)


def load_blockchain_config(settings: Settings) -> BlockchainConfig | None:
    """None when the feature is off; raises if it is on but unsafe or incomplete."""
    if not settings.blockchain_enabled:
        return None
    chain_id = settings.blockchain_chain_id
    if chain_id not in ALLOWED_CHAIN_IDS:
        raise BlockchainConfigError(
            f"BLOCKCHAIN_CHAIN_ID {chain_id} is not an allowed test network "
            f"{sorted(ALLOWED_CHAIN_IDS)}"
        )
    return BlockchainConfig(
        rpc_url=_rpc_url(settings.blockchain_rpc_url, chain_id),
        chain_id=chain_id,
        contracts=_load_contracts(settings.blockchain_deployment_path, chain_id),
        accounts=_load_accounts(settings, chain_id),
    )


def _rpc_url(url: str, chain_id: int) -> str:
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise BlockchainConfigError("BLOCKCHAIN_RPC_URL must be an http(s) URL")
    if chain_id != LOCAL_CHAIN_ID and parts.scheme != "https":
        raise BlockchainConfigError("BLOCKCHAIN_RPC_URL must use https on a public network")
    return url


def _load_contracts(path_setting: str, chain_id: int) -> dict[str, str]:
    path = Path(path_setting)
    if not path.is_absolute():
        path = REPO_ROOT / path
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        deployed_chain = data["chainId"]
        contracts = data["contracts"]
        missing = [name for name in REQUIRED_CONTRACTS if not is_address(contracts.get(name))]
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
        raise BlockchainConfigError(
            f"Could not read the deployment file {path}. For the local chain, run "
            "`npm run deploy:local` in blockchain/"
        ) from exc
    if deployed_chain != chain_id:
        raise BlockchainConfigError(
            f"The deployment file is for chain {deployed_chain}, "
            f"but BLOCKCHAIN_CHAIN_ID is {chain_id}"
        )
    if missing:
        raise BlockchainConfigError(
            f"Deployment file has no valid address for: {', '.join(missing)}"
        )
    return {name: to_checksum_address(contracts[name]) for name in REQUIRED_CONTRACTS}


def _load_accounts(settings: Settings, chain_id: int) -> dict[str, LocalAccount]:
    accounts: dict[str, LocalAccount] = {}
    for role in ROLES:
        name = f"blockchain_{role}_private_key"
        secret = getattr(settings, name)
        value = secret.get_secret_value().strip() if secret else ""
        if not value:
            raise BlockchainConfigError(f"{name.upper()} is not set")
        # The library pads a short key into a different one, so check the length first.
        if not _PRIVATE_KEY.fullmatch(value):
            raise BlockchainConfigError(f"{name.upper()} is not a valid private key")
        try:
            accounts[role] = Account.from_key(value)
        except (ValueError, TypeError):
            # `from None`: the library's own error could quote the key.
            raise BlockchainConfigError(f"{name.upper()} is not a valid private key") from None
    addresses = {account.address for account in accounts.values()}
    if len(addresses) != len(ROLES):
        raise BlockchainConfigError("Each blockchain role needs a different private key")
    if chain_id != LOCAL_CHAIN_ID and addresses & _hardhat_addresses():
        raise BlockchainConfigError(
            "Hardhat's public test keys can't be used on a public network"
        )
    return accounts


def _hardhat_addresses() -> set[str]:
    Account.enable_unaudited_hdwallet_features()
    return {
        Account.from_mnemonic(_HARDHAT_MNEMONIC, account_path=f"m/44'/60'/0'/0/{i}").address
        for i in range(20)
    }
