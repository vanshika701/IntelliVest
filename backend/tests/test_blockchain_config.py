"""Blockchain settings: off by default, and refused when unsafe (Phase 10, B9)."""

import json
import subprocess
import sys

import pytest
from eth_account import Account
from fastapi.testclient import TestClient

from app.core.config import Settings, settings
from app.main import app
from app.services.blockchain import config as bc

# Hardhat's published account 0. Not a secret.
HARDHAT_KEY_0 = "0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80"


def _deployment(tmp_path, chain_id=31337, drop=None):
    contracts = {n: f"0x{i + 1:040x}" for i, n in enumerate(bc.REQUIRED_CONTRACTS) if n != drop}
    path = tmp_path / "deployment.json"
    path.write_text(json.dumps({"chainId": chain_id, "contracts": contracts}), encoding="utf-8")
    return str(path)


def _settings(tmp_path, chain_id=31337, **over):
    values = {f"blockchain_{role}_private_key": Account.create().key.hex() for role in bc.ROLES}
    local = chain_id == bc.LOCAL_CHAIN_ID
    values |= {
        "blockchain_enabled": True,
        "blockchain_chain_id": chain_id,
        "blockchain_rpc_url": "http://127.0.0.1:8545" if local else "https://rpc.example",
        "blockchain_deployment_path": _deployment(tmp_path, chain_id),
    }
    return Settings(_env_file=None, **(values | over))


def test_off_by_default():
    assert Settings.model_fields["blockchain_enabled"].default is False


def test_off_needs_nothing_else():
    config = Settings(_env_file=None, blockchain_enabled=False, blockchain_chain_id=1)
    assert bc.load_blockchain_config(config) is None


def test_app_does_not_import_web3_when_off():
    code = "import sys, app.main; sys.exit(any(m in sys.modules for m in ('web3', 'eth_account')))"
    assert subprocess.run([sys.executable, "-c", code], timeout=120, check=False).returncode == 0


def test_valid_local_config(tmp_path):
    config = bc.load_blockchain_config(_settings(tmp_path))
    assert set(config.accounts) == set(bc.ROLES)
    assert set(config.contracts) == set(bc.REQUIRED_CONTRACTS)


def test_valid_sepolia_config(tmp_path):
    assert bc.load_blockchain_config(_settings(tmp_path, 11155111)).chain_id == 11155111


@pytest.mark.parametrize("chain_id", [1, 137, 0])
def test_refuses_real_money_networks(tmp_path, chain_id):
    with pytest.raises(bc.BlockchainConfigError, match="not an allowed test network"):
        bc.load_blockchain_config(_settings(tmp_path, chain_id))


@pytest.mark.parametrize("role", bc.ROLES)
def test_every_role_needs_a_key(tmp_path, role):
    for empty in (None, "", "  "):
        over = {f"blockchain_{role}_private_key": empty}
        with pytest.raises(bc.BlockchainConfigError, match="is not set"):
            bc.load_blockchain_config(_settings(tmp_path, **over))


def test_refuses_a_shared_key(tmp_path):
    key = Account.create().key.hex()
    shared = {"blockchain_stock_private_key": key, "blockchain_advisor_private_key": "0x" + key}
    with pytest.raises(bc.BlockchainConfigError, match="different private key"):
        bc.load_blockchain_config(_settings(tmp_path, **shared))


def test_public_hardhat_keys_only_work_locally(tmp_path):
    key = {"blockchain_relayer_private_key": HARDHAT_KEY_0}
    assert bc.load_blockchain_config(_settings(tmp_path, **key))
    with pytest.raises(bc.BlockchainConfigError, match="public test keys"):
        bc.load_blockchain_config(_settings(tmp_path, 11155111, **key))


@pytest.mark.parametrize("url", ["", "localhost:8545", "ws://x", "http://rpc.example"])
def test_refuses_bad_public_rpc_urls(tmp_path, url):
    with pytest.raises(bc.BlockchainConfigError, match="BLOCKCHAIN_RPC_URL"):
        bc.load_blockchain_config(_settings(tmp_path, 11155111, blockchain_rpc_url=url))


@pytest.mark.parametrize("text", [None, "[]", "not json", '{"chainId": 31337, "contracts": null}'])
def test_refuses_missing_or_broken_deployment_file(tmp_path, text):
    path = tmp_path / "broken.json"
    if text is not None:
        path.write_text(text, encoding="utf-8")
    with pytest.raises(bc.BlockchainConfigError, match="deploy:local"):
        bc.load_blockchain_config(_settings(tmp_path, blockchain_deployment_path=str(path)))


def test_refuses_deployment_for_another_chain(tmp_path):
    config = _settings(tmp_path)
    _deployment(tmp_path, 80002)
    with pytest.raises(bc.BlockchainConfigError, match="for chain 80002"):
        bc.load_blockchain_config(config)


def test_refuses_incomplete_deployment(tmp_path):
    config = _settings(tmp_path)
    _deployment(tmp_path, drop="AITaskManager")
    with pytest.raises(bc.BlockchainConfigError, match="AITaskManager"):
        bc.load_blockchain_config(config)


def test_keys_never_appear_in_output(tmp_path):
    valid = _settings(tmp_path)
    key = valid.blockchain_advisor_private_key.get_secret_value()
    shown = repr(valid) + str(valid.model_dump()) + repr(bc.load_blockchain_config(valid))
    assert key not in shown
    bad = _settings(tmp_path, blockchain_advisor_private_key="zz-not-a-key")
    with pytest.raises(bc.BlockchainConfigError) as error:
        bc.load_blockchain_config(bad)
    assert "zz-not-a-key" not in str(error.value)


@pytest.mark.parametrize("key", ["a" * 63, "a" * 65, "0x" + "0" * 64, "0x" + "f" * 64])
def test_refuses_malformed_keys(tmp_path, key):
    with pytest.raises(bc.BlockchainConfigError, match="ADVISOR_PRIVATE_KEY is not a valid"):
        bc.load_blockchain_config(_settings(tmp_path, blockchain_advisor_private_key=key))


def test_app_refuses_to_start_when_enabled_but_misconfigured(monkeypatch):
    monkeypatch.setattr(settings, "enable_scheduler", False)
    monkeypatch.setattr(settings, "blockchain_enabled", True)
    monkeypatch.setattr(settings, "blockchain_chain_id", 1)
    with pytest.raises(bc.BlockchainConfigError), TestClient(app):
        pass
