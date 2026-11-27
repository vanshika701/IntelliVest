"""What the frontend needs to know before showing blockchain screens (B11).

Reads settings and the public deployment file only: no keys, no chain call.
"""

import json
from pathlib import Path

from app.core.config import settings

REPO_ROOT = Path(__file__).resolve().parents[4]
NETWORKS = {31337: "Hardhat (local)", 11155111: "Ethereum Sepolia", 80002: "Polygon Amoy"}
PRIVACY_NOTICE = (
    "Test tokens only; no real money. On a public network, your vault's balances, mandate limits "
    "and trades can be seen by anyone. IntelliVest never puts your name, email, income, expenses, "
    "goals or article text on-chain, only hashes and numbers. A signed AI result shows who sent it, "
    "not that the model is right; a trade inside your limits can still lose money."
)


def blockchain_status() -> dict:
    if not settings.blockchain_enabled:
        return {"enabled": False, "privacy_notice": PRIVACY_NOTICE}
    return {
        "enabled": True,
        "chain_id": settings.blockchain_chain_id,
        "network": NETWORKS.get(settings.blockchain_chain_id),
        "contracts": _contracts(),
        "models": _models(),
        "privacy_notice": PRIVACY_NOTICE,
    }


def _models() -> list[dict]:
    """The model versions a mandate should accept, with their registry keys."""
    from app.services.blockchain import hashing
    from app.services.blockchain.mock_advisor import MockAdvisor
    from app.services.blockchain.stock_evidence import MODEL_NAME as STOCK_MODEL

    advisor = MockAdvisor()
    entries = [
        ("sentiment", settings.sentiment_model, settings.blockchain_sentiment_model_version),
        ("stock_prediction", STOCK_MODEL, settings.blockchain_stock_model_version),
        ("advisor", advisor.model_name, advisor.model_version),
    ]
    return [
        {
            "step": step,
            "name": name,
            "version": version,
            "key": "0x"
            + hashing.model_key(hashing.model_id(name), hashing.model_id(version)).hex(),
            "mock": step == "advisor",
        }
        for step, name, version in entries
        if version
    ]


def _contracts() -> dict[str, str]:
    path = Path(settings.blockchain_deployment_path)
    if not path.is_absolute():
        path = REPO_ROOT / path
    try:
        return dict(json.loads(path.read_text(encoding="utf-8"))["contracts"])
    except (OSError, ValueError, KeyError, TypeError):
        return {}
