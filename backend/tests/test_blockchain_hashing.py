"""Python must hash exactly what the contracts hash (Phase 10)."""

import json
from pathlib import Path

import pytest
from eth_account import Account

from app.services.blockchain import hashing

VECTORS = json.loads(
    (Path(__file__).resolve().parents[2] / "blockchain" / "test-vectors" / "signing.json").read_text(encoding="utf-8")
)


def _message(name: str) -> dict:
    message = dict(VECTORS[name]["message"])
    for key in ("amount", "minimumReceived", "nonce"):
        if key in message:
            message[key] = int(message[key])
    return message


@pytest.mark.parametrize("name", ["Evidence", "Proposal"])
def test_matches_contract_vectors(name):
    signable = hashing.typed_message(name, VECTORS["domain"], _message(name))
    assert "0x" + signable.body.hex() == VECTORS[name]["structHash"]
    assert "0x" + hashing.typed_digest(signable).hex() == VECTORS[name]["digest"]


@pytest.mark.parametrize("name", ["Evidence", "Proposal"])
def test_field_order_matches_contract(name):
    assert hashing._FIELDS[name] == VECTORS[name]["types"]


def test_sign_and_recover():
    account = Account.create()
    message = _message("Proposal")
    signature = hashing.sign("Proposal", VECTORS["domain"], message, account.key.hex())
    assert hashing.recover("Proposal", VECTORS["domain"], message, signature) == account.address
    changed = {**message, "amount": message["amount"] + 1}
    assert hashing.recover("Proposal", VECTORS["domain"], changed, signature) != account.address


def test_canonical_json_ignores_key_order_and_rejects_floats():
    assert hashing.hash_data({"a": 1, "b": "₹"}) == hashing.hash_data({"b": "₹", "a": 1})
    for bad in (1.5, {"x": [1, {"y": 0.1}]}):
        with pytest.raises(TypeError):
            hashing.hash_data(bad)


def test_salt_changes_private_hash():
    assert hashing.hash_private({"x": 1}, hashing.new_salt()) != hashing.hash_private({"x": 1}, hashing.new_salt())
