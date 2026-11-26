"""Phase 9 → Phase 10 bridge: turn the "invest per plan" action into draft
trade proposals in the frozen `Proposal` format (blockchain/contracts/Types.sol,
checklist B20), with the hashes that tie each draft to its explanation and
the modules it came from.

Drafts only. The fields Phase 10's worker fills once B10-B13 exist are left
None and listed in `pending_fields`: the vault and fund token addresses
(from the deployment file), the minimum received (needs the price feed),
the nonce and deadline, the on-chain task id and the evidence chain hash.
Nothing here signs or sends anything.

Formats follow docs/PHASE_10_BLOCKCHAIN.md: canonical JSON then keccak256,
integers only (6-decimal test tokens, scores out of 10000), and a random
salt on anything derived from private data (amounts, holdings, goals).
"""

from datetime import date, datetime

from app.core.advisor_config import ADVISOR_VERSION

TOKEN_DECIMALS = 6
SIDE_BUY = 0  # Types.sol: enum Side { BUY, SELL }
ADVISOR_MODEL_ID = "intellivest-advisor"

# Confidence here is confidence in the INPUTS, not in the outcome: the
# advisor is rules, not a model with a probability. A contributor with fresh
# data counts fully, stale data half. Phase 10 can only use confidence to make
# a check stricter (e.g. ask the owner to sign), never to bypass a limit.
STATUS_WEIGHT = {"ok": 1.0, "stale": 0.5}

PENDING_FIELDS = ["taskId", "vault", "fund", "minimumReceived", "nonce", "deadline", "evidenceHash"]


def hashable(value):
    """Canonical-JSON-safe copy: floats become fixed 6-decimal strings,
    dates ISO strings. Deterministic, so the same data always hashes the same."""
    if isinstance(value, float):
        return f"{value:.6f}"
    if isinstance(value, datetime | date):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(k): hashable(v) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [hashable(v) for v in value]
    return value


def hex32(digest: bytes) -> str:
    return "0x" + digest.hex()


def to_token_units(rupees: float) -> int:
    """₹ to tINR base units (6 decimals), exact for whole paise."""
    return round(rupees * 100) * 10 ** (TOKEN_DECIMALS - 2)


def confidence(contributors: list[str], modules: dict[str, dict]) -> int:
    weights = [STATUS_WEIGHT.get(modules[c]["status"], 0.0) for c in contributors]
    return round(10_000 * min(weights)) if weights else 0


def build_proposal_drafts(actions: list[dict], modules: list[dict], salt: str | None = None) -> dict:
    """Drafts for the one-time amounts of the invest-per-plan action.

    Monthly SIPs are left out: Phase 10 runs those as vault SIPs (B16), not
    as advisor trades. Returns {"salt", "drafts"}; the salt stays off-chain
    with the advice so every hash can be checked later."""
    # Imported here, not at module load: with BLOCKCHAIN_ENABLED off the app
    # must not load web3 / eth_account (tests/test_blockchain_config.py).
    from app.services.blockchain.hashing import hash_private, hash_text, new_salt

    invest = next((a for a in actions if a["id"] == "invest_per_plan"), None)
    by_id = {m["module"]: m for m in modules}
    plan = by_id.get("portfolio_plan")
    if invest is None or plan is None or plan["status"] not in STATUS_WEIGHT:
        return {"salt": None, "drafts": []}

    salt = salt or new_salt()
    contributions = [
        {"module": c, "status": by_id[c]["status"], "version": by_id[c]["version"],
         "as_of": by_id[c]["as_of"], "data_hash": hex32(hash_private(hashable(by_id[c]["data"]), salt))}
        for c in invest["contributors"]
    ]
    explanation = {"title": invest["title"], "detail": invest["detail"], "facts": invest["facts"]}
    shared = {
        "side": SIDE_BUY,
        "confidence": confidence(invest["contributors"], by_id),
        "modelId": hex32(hash_text(ADVISOR_MODEL_ID)),
        "modelVersion": hex32(hash_text(ADVISOR_VERSION)),
        "explanationHash": hex32(hash_private(hashable(explanation), salt)),
    }
    drafts = []
    for h in plan["data"]["holdings"]:
        if not h["instrument_id"] or h["lump_sum_amount"] <= 0:
            continue
        inputs = {"instrument_id": h["instrument_id"], "lump_sum_amount": h["lump_sum_amount"],
                  "weight": h["weight"], "plan_id": plan["data"]["id"]}
        drafts.append({
            **dict.fromkeys(PENDING_FIELDS),
            **shared,
            "amount": to_token_units(h["lump_sum_amount"]),
            "inputHash": hex32(hash_private(hashable(inputs), salt)),
            # Off-chain context for the worker and for explaining the trade later.
            "instrument_id": h["instrument_id"],
            "name": h["name"],
            "asset_class": h["asset_class"],
            "rupees": h["lump_sum_amount"],
        })
    return {
        "salt": salt,
        "drafts": drafts,
        "contributions": contributions,
        "explanation": explanation,
        "pending_fields": PENDING_FIELDS,
        "note": ("Drafts in the Phase 10 Proposal format. Not signed or sent; the pending fields are "
                 "filled by the Phase 10 worker (checklist B10-B12)."),
    }
