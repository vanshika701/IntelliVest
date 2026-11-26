"""Phase 9 → Phase 10 bridge: drafts in the frozen Proposal format."""

from datetime import UTC, datetime

import pytest

from app.services.advisor.modules import module_result
from app.services.advisor.proposal import (
    PENDING_FIELDS,
    build_proposal_drafts,
    confidence,
    hashable,
    hex32,
    to_token_units,
)
from app.services.blockchain.hashing import PROPOSAL_FIELDS, canonical_json, hash_private

NOW = datetime(2026, 11, 27, tzinfo=UTC)
SALT = "0x" + "11" * 32


def _modules(plan_status: str = "ok") -> list[dict]:
    plan = module_result("portfolio_plan", plan_status, as_of=NOW, version="rec-v1", data={
        "id": "r1",
        "holdings": [
            {"instrument_id": "stock-TCS.NS", "name": "TCS", "asset_class": "equity", "weight": 0.2,
             "lump_sum_amount": 20_000, "monthly_amount": 2_000},
            {"instrument_id": "mf-118987", "name": "HDFC Corporate Bond", "asset_class": "debt", "weight": 0.8,
             "lump_sum_amount": 80_000.5, "monthly_amount": 8_000},
            {"instrument_id": None, "name": "Gold (no fund available)", "asset_class": "gold", "weight": 0.0,
             "lump_sum_amount": 0, "monthly_amount": 0},
        ],
    })
    risk = module_result("risk_profile", "ok", version="risk-v1", data={"profile": "moderate", "score": 62.5})
    return [risk, plan]


INVEST = {"id": "invest_per_plan", "title": "Invest ₹1,00,000 now", "detail": "45% stocks…",
          "facts": ["Risk profile: Moderate."], "contributors": ["risk_profile", "portfolio_plan"]}


def test_drafts_match_the_frozen_proposal_fields() -> None:
    out = build_proposal_drafts([INVEST], _modules(), salt=SALT)
    assert [d["instrument_id"] for d in out["drafts"]] == ["stock-TCS.NS", "mf-118987"]  # no ₹0 or fund-less lines
    frozen = {f["name"] for f in PROPOSAL_FIELDS}
    for draft in out["drafts"]:
        assert frozen <= set(draft), "every frozen Proposal field must be present"
        assert all(draft[f] is None for f in PENDING_FIELDS)
        assert draft["side"] == 0 and draft["confidence"] == 10_000
        for key in ("modelId", "modelVersion", "inputHash", "explanationHash"):
            assert draft[key].startswith("0x") and len(draft[key]) == 66
    assert out["pending_fields"] == PENDING_FIELDS


def test_amounts_are_six_decimal_token_units() -> None:
    assert to_token_units(20_000) == 20_000_000_000
    assert to_token_units(80_000.5) == 80_000_500_000
    drafts = build_proposal_drafts([INVEST], _modules(), salt=SALT)["drafts"]
    assert [d["amount"] for d in drafts] == [20_000_000_000, 80_000_500_000]
    assert all(isinstance(d["amount"], int) for d in drafts)


def test_hashes_are_deterministic_salted_and_checkable() -> None:
    first = build_proposal_drafts([INVEST], _modules(), salt=SALT)
    again = build_proposal_drafts([INVEST], _modules(), salt=SALT)
    other = build_proposal_drafts([INVEST], _modules(), salt="0x" + "22" * 32)
    assert first["drafts"] == again["drafts"]
    assert first["drafts"][0]["inputHash"] != other["drafts"][0]["inputHash"]
    # Anyone holding the salt can recompute the explanation hash.
    expected = hex32(hash_private(hashable(first["explanation"]), SALT))
    assert first["drafts"][0]["explanationHash"] == expected
    assert len(first["contributions"]) == 2 and first["contributions"][1]["module"] == "portfolio_plan"
    assert build_proposal_drafts([INVEST], _modules())["salt"].startswith("0x")  # fresh salt by default


def test_hashable_removes_floats_and_dates() -> None:
    data = hashable({"w": 0.1 + 0.2, "when": NOW, "list": [1.5, {"x": 2}]})
    assert data == {"w": "0.300000", "when": NOW.isoformat(), "list": ["1.500000", {"x": 2}]}
    canonical_json(data)  # would raise on any float left


@pytest.mark.parametrize(("statuses", "expected"), [(["ok", "ok"], 10_000), (["ok", "stale"], 5_000), ([], 0)])
def test_confidence_reflects_input_freshness(statuses: list[str], expected: int) -> None:
    modules = {f"m{i}": {"status": s} for i, s in enumerate(statuses)}
    assert confidence(list(modules), modules) == expected


def test_no_drafts_without_an_invest_action_or_a_usable_plan() -> None:
    assert build_proposal_drafts([], _modules())["drafts"] == []
    assert build_proposal_drafts([INVEST], _modules("unavailable"))["drafts"] == []
    stale = build_proposal_drafts([INVEST], _modules("stale"), salt=SALT)["drafts"]
    assert stale and stale[0]["confidence"] == 5_000
