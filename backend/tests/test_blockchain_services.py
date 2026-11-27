"""Signing, advisor interface, mock advisor and stock evidence (Phase 10, B10).

No chain needed; test_blockchain_chain.py runs the same code against Hardhat.
"""

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from eth_account import Account

from app.services.blockchain import hashing
from app.services.blockchain.advisor import (
    AdvisorDecision,
    AdvisorRequest,
    build_proposal,
    expected_out,
    proposal_nonce,
)
from app.services.blockchain.formats import (
    Evidence,
    EvidenceResult,
    EvidenceStatus,
    Reason,
    Side,
    Step,
)
from app.services.blockchain.mock_advisor import MockAdvisor
from app.services.blockchain.signing import RoleSigner
from app.services.blockchain.stock_evidence import MODEL_NAME, build_stock_evidence, model_ref

ROOT = Path(__file__).resolve().parents[2]
VECTORS = json.loads(
    (ROOT / "blockchain" / "test-vectors" / "signing.json").read_text(encoding="utf-8")
)
TASK = bytes.fromhex(VECTORS["Evidence"]["message"]["taskId"][2:])
NOW = datetime(2026, 11, 27, 12, tzinfo=UTC)
U = 1_000_000


def _vector(name: str) -> dict:
    m = dict(VECTORS[name]["message"])
    for key, value in m.items():
        if isinstance(value, str) and value.startswith("0x") and len(value) == 66:
            m[key] = bytes.fromhex(value[2:])
        elif key in ("amount", "minimumReceived", "nonce"):
            m[key] = int(value)
    return m


def _record(**over) -> dict:
    return {
        "ticker": "RELIANCE",
        "as_of": datetime(2026, 11, 26, tzinfo=UTC),
        "horizon_days": 5,
        "chance_beat": 0.62,
        "target": "excess_log_return_vs_nifty",
        "low": -0.031,
        "mid": 0.004,
        "high": 0.04,
        "model_version": "v3",
        "artifact_hash": "ab" * 32,
        **over,
    }


def _evidence(step: Step, score: int, status=EvidenceStatus.OK) -> EvidenceResult:
    e = Evidence(
        TASK, int(step), int(status), bytes(32), bytes(32), bytes(32), bytes(32), score, 0, 0, 0
    )
    return EvidenceResult(e, {}, {})


def _request(*evidence: EvidenceResult, cash=10_000 * U, units=0) -> AdvisorRequest:
    return AdvisorRequest(
        task_id=TASK,
        vault="0x00000000000000000000000000000000000000BB",
        fund="0x00000000000000000000000000000000000000CC",
        fund_label="tEquityFund",
        is_equity=True,
        price=100 * U,
        cash=cash,
        units=units,
        max_slippage_bps=100,
        evidence=evidence,
    )


# --- Formats ---


def test_enums_match_solidity():
    source = (ROOT / "blockchain" / "contracts" / "Types.sol").read_text(encoding="utf-8")
    reasons = source.split("enum Reason {")[1].split("}")[0].replace(",", " ").split()
    assert [r.name for r in Reason] == reasons
    assert "enum Step { NONE, SENTIMENT, STOCK_PREDICTION, ADVISOR }" in source


@pytest.mark.parametrize("name", ["Evidence", "Proposal"])
def test_struct_hash_matches_vectors(name):
    assert "0x" + hashing.struct_hash(name, _vector(name)).hex() == VECTORS[name]["structHash"]


def test_model_key_and_evidence_chain():
    # Values from ethers: keccak256(abi.encode(bytes32, bytes32)).
    model, version = hashing.model_id("mock-advisor"), hashing.model_id("v1")
    assert hashing.model_key(model, version) == hashing.keccak(model + version)
    assert model == hashing.keccak(text="mock-advisor")
    first = hashing.chain_evidence(hashing.ZERO_HASH, b"\x01" * 32)
    assert first != hashing.chain_evidence(hashing.ZERO_HASH, b"\x02" * 32)
    assert len(first) == 32


def test_role_signer_signs_for_the_task_manager_domain():
    account = Account.create()
    domain = VECTORS["domain"]
    signer = RoleSigner(account, domain["chainId"], domain["verifyingContract"])
    evidence = Evidence(**_vector("Evidence"))
    signed = signer.sign_evidence(evidence)
    assert (
        hashing.recover("Evidence", domain, evidence.message(), signed.signature) == account.address
    )
    other = hashing.domain(1, domain["verifyingContract"])
    assert (
        hashing.recover("Evidence", other, evidence.message(), signed.signature) != account.address
    )
    assert account.key.hex() not in repr(signer)


# --- Stock evidence (real Phase 4 records) ---


def test_stock_evidence_from_stored_prediction():
    result = build_stock_evidence(TASK, "RELIANCE", 5, [_record()], NOW, "v3")
    e = result.evidence
    assert (e.step, e.status, e.score, e.horizonDays) == (
        Step.STOCK_PREDICTION,
        EvidenceStatus.OK,
        6200,
        5,
    )
    assert e.asOf == int(datetime(2026, 11, 26, tzinfo=UTC).timestamp())
    assert e.modelId == hashing.model_id(MODEL_NAME) and e.modelVersion == hashing.model_id("v3")
    assert result.outputs == {
        "chance_beat_bps": 6200,
        "low_bps": -310,
        "mid_bps": 40,
        "high_bps": 400,
    }
    assert e.inputHash == hashing.hash_data(result.inputs)
    assert e.outputHash == hashing.hash_data(result.outputs)
    assert result.inputs["artifact_hash"] == "ab" * 32


def test_stock_evidence_picks_nearest_horizon_and_tolerates_missing_extras():
    records = [
        _record(horizon_days=1, chance_beat=0.4),
        _record(horizon_days=20, chance_beat=0.7, low=None),
    ]
    result = build_stock_evidence(TASK, "RELIANCE", 15, records, NOW, "v3")
    assert result.evidence.horizonDays == 20 and result.evidence.score == 7000
    assert "low_bps" not in result.outputs


def test_naive_mongo_dates_are_utc():
    naive = _record(as_of=datetime(2026, 11, 26, tzinfo=UTC).replace(tzinfo=None))
    assert build_stock_evidence(TASK, "X", 5, [naive], NOW, "v3").evidence.asOf == int(
        datetime(2026, 11, 26, tzinfo=UTC).timestamp()
    )


@pytest.mark.parametrize(
    "records",
    [
        [],
        [_record(as_of=NOW - timedelta(days=8))],
        [_record(model_version="v4")],  # retrained but not registered yet
        [_record(chance_beat=None)],
    ],
)
def test_stock_evidence_without_usable_prediction_is_no_data(records):
    e = build_stock_evidence(TASK, "RELIANCE", 5, records, NOW, "v3").evidence
    assert e.status == EvidenceStatus.NO_DATA and e.score == 0
    # Still signed under the registered version, or the contract would revert.
    assert e.modelVersion == hashing.model_id("v3")
    assert e.asOf == int(NOW.timestamp())


def test_model_ref_uses_artifact_hash():
    _, version, artifact = model_ref(_record())
    assert artifact == bytes.fromhex("ab" * 32) and version == hashing.model_id("v3")


# --- Mock advisor and proposal building ---


async def test_mock_advisor_buys_on_bullish_evidence():
    request = _request(_evidence(Step.STOCK_PREDICTION, 7000), _evidence(Step.SENTIMENT, 3000))
    decision = await MockAdvisor().decide(request)
    assert decision.side == Side.BUY and decision.amount == 1_000 * U
    assert decision.confidence == 5000 + (4000 + 3000) // 2 // 2
    assert set(decision.contributions) == {"stock_prediction", "sentiment"}


async def test_mock_advisor_sells_only_what_it_holds():
    bearish = (_evidence(Step.STOCK_PREDICTION, 2000), _evidence(Step.SENTIMENT, -4000))
    assert (await MockAdvisor().decide(_request(*bearish, units=40 * U))).amount == 10 * U
    assert await MockAdvisor().decide(_request(*bearish, units=0)) is None


async def test_mock_advisor_ignores_no_data_and_fallback():
    request = _request(
        _evidence(Step.STOCK_PREDICTION, 9000, EvidenceStatus.NO_DATA),
        _evidence(Step.SENTIMENT, 9000, EvidenceStatus.FALLBACK),
    )
    assert await MockAdvisor().decide(request) is None


async def test_mock_advisor_holds_when_neutral():
    assert await MockAdvisor().decide(_request(_evidence(Step.STOCK_PREDICTION, 5200))) is None


def test_build_proposal_hashes_and_limits():
    request = _request(_evidence(Step.STOCK_PREDICTION, 7000))
    decision = AdvisorDecision(
        Side.BUY, 1_000 * U, 7000, "why", {"stock_prediction": {}}, {"goal": "house"}
    )
    advisor = MockAdvisor()
    draft = build_proposal(
        request, decision, advisor, b"\x07" * 32, proposal_nonce(TASK), 1_790_003_600
    )
    p = draft.proposal
    assert (
        p.minimumReceived == expected_out(Side.BUY, 1_000 * U, 100 * U) * 9900 // 10000 == 9_900_000
    )
    assert p.modelId == hashing.model_id(advisor.model_name)
    assert p.evidenceHash == b"\x07" * 32 and p.nonce == int.from_bytes(TASK, "big")
    salt = draft.record["salt"]
    assert p.inputHash == hashing.hash_private(draft.record["inputs"], salt)
    assert p.explanationHash == hashing.hash_private(draft.record["explanation"], salt)
    # Salted: private inputs can't be guessed from the hash.
    assert p.inputHash != hashing.hash_data(draft.record["inputs"])
    assert expected_out(Side.SELL, 10 * U, 100 * U) == 1_000 * U


@pytest.mark.parametrize("over", [{"confidence": 10_001}, {"confidence": -1}, {"amount": 0}])
def test_build_proposal_rejects_bad_decisions(over):
    values = {"side": Side.BUY, "amount": U, "confidence": 5000, "explanation": "x"} | over
    with pytest.raises(ValueError):
        build_proposal(_request(), AdvisorDecision(**values), MockAdvisor(), bytes(32), 1, 1)
