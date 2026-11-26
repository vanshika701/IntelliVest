"""Phase 9 advice service: gather every module (adapters.py), apply the
rules (rules.py), summarise, store.

Reads only precomputed or cached data, each module under its own timeout,
so it is safe inside a request and never fails because one module did.
"""

from datetime import UTC, datetime

from app.core.advisor_config import ADVISOR_VERSION, DISCLAIMER
from app.data import advice_repository
from app.services.advisor.adapters import gather_modules
from app.services.advisor.proposal import build_proposal_drafts
from app.services.advisor.rules import build_actions
from app.services.advisor.summary import summarize


async def create_advice(user_id: str, now: datetime | None = None) -> dict:
    now = now or datetime.now(UTC)
    modules = await gather_modules(user_id, now)
    result = build_actions(modules)
    doc = {
        **result,
        "summary": await summarize(result),
        "modules": modules,
        # Phase 10 bridge (checklist B20): drafts only, nothing is signed or sent.
        "proposals": build_proposal_drafts(result["actions"], modules),
        "version": ADVISOR_VERSION,
        "disclaimer": DISCLAIMER,
        "created_at": now,
    }
    return await advice_repository.insert_advice(user_id, doc)


async def get_latest_advice(user_id: str) -> dict | None:
    return await advice_repository.get_latest_advice(user_id)
