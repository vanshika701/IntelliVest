"""Hash and signing formats shared with the contracts (Phase 10).

Must match blockchain/contracts/Types.sol. Both sides are checked against
blockchain/test-vectors/signing.json.
"""

import json
import secrets
from typing import Any

from eth_account import Account
from eth_account.messages import SignableMessage, encode_typed_data
from eth_utils import keccak


def _fields(*pairs: tuple[str, str]) -> list[dict[str, str]]:
    return [{"type": kind, "name": name} for kind, name in pairs]


EVIDENCE_FIELDS = _fields(
    ("bytes32", "taskId"), ("uint8", "step"), ("uint8", "status"), ("bytes32", "modelId"),
    ("bytes32", "modelVersion"), ("bytes32", "inputHash"), ("bytes32", "outputHash"), ("int32", "score"),
    ("uint32", "count"), ("uint32", "horizonDays"), ("uint64", "asOf"),
)
PROPOSAL_FIELDS = _fields(
    ("bytes32", "taskId"), ("address", "vault"), ("address", "fund"), ("uint8", "side"), ("uint256", "amount"),
    ("uint256", "minimumReceived"), ("uint16", "confidence"), ("bytes32", "modelId"), ("bytes32", "modelVersion"),
    ("bytes32", "inputHash"), ("bytes32", "evidenceHash"), ("bytes32", "explanationHash"), ("uint256", "nonce"),
    ("uint64", "deadline"),
)
_FIELDS = {"Evidence": EVIDENCE_FIELDS, "Proposal": PROPOSAL_FIELDS}


def _reject_floats(value: Any) -> None:
    if isinstance(value, float):
        raise TypeError("Floats are not allowed in hashed data; use integers or strings")
    if isinstance(value, dict):
        if not all(isinstance(key, str) for key in value):
            raise TypeError("Hashed data needs string keys")
        for item in value.values():
            _reject_floats(item)
    elif isinstance(value, list | tuple):
        for item in value:
            _reject_floats(item)


def canonical_json(data: Any) -> bytes:
    """Sorted keys, no spaces, UTF-8, no floats."""
    _reject_floats(data)
    return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode()


def hash_data(data: Any) -> bytes:
    return keccak(canonical_json(data))


def new_salt() -> str:
    return "0x" + secrets.token_hex(32)


def hash_private(data: Any, salt: str) -> bytes:
    """For anything derived from private data. Store the salt off-chain."""
    return hash_data({"data": data, "salt": salt})


def hash_text(text: str) -> bytes:
    return keccak(text=text)


def typed_message(name: str, domain: dict, message: dict) -> SignableMessage:
    return encode_typed_data(domain_data=domain, message_types={name: _FIELDS[name]}, message_data=message)


def typed_digest(signable: SignableMessage) -> bytes:
    return keccak(b"\x19" + signable.version + signable.header + signable.body)


def sign(name: str, domain: dict, message: dict, private_key: str) -> bytes:
    return bytes(Account.sign_message(typed_message(name, domain, message), private_key).signature)


def recover(name: str, domain: dict, message: dict, signature: bytes) -> str:
    return Account.recover_message(typed_message(name, domain, message), signature=signature)


def domain(chain_id: int, task_manager: str) -> dict:
    """EIP-712 domain of AITaskManager."""
    return {"name": "IntelliVest", "version": "1", "chainId": chain_id, "verifyingContract": task_manager}


def struct_hash(name: str, message: dict) -> bytes:
    return bytes(typed_message(name, {"name": "x"}, message).body)


def model_id(name: str) -> bytes:
    """bytes32 for a model or version name, like ethers.id()."""
    return keccak(text=name)


def model_key(model: bytes, version: bytes) -> bytes:
    """ModelRegistry.keyOf: keccak256(abi.encode(modelId, version))."""
    return keccak(model + version)


def chain_evidence(previous: bytes, evidence_struct_hash: bytes) -> bytes:
    """AITaskManager's running evidence hash: keccak256(abi.encode(previous, structHash))."""
    return keccak(previous + evidence_struct_hash)


ZERO_HASH = bytes(32)
