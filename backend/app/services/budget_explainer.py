"""Optional friendly wording for the budget engine's output (Phase 8).

The rules engine and goal planner produce every number, flag and
recommendation, plus template sentences. This layer may only REPHRASE
those sentences:

- provider "template" (default): returns the engine's own sentences.
- provider "anthropic": asks Claude to rewrite them in plain, friendly
  language. The reply is rejected (template used instead) if it contains
  any number that wasn't in the input, so the LLM can't invent or alter
  figures. Any error, refusal or missing SDK also falls back to the template.

The LLM is never used for categorisation or for any decision.
"""

import logging
import re

from app.core.config import settings

logger = logging.getLogger(__name__)

_NUMBER_RE = re.compile(r"\d[\d,]*(?:\.\d+)?")

_SYSTEM_PROMPT = (
    "You rewrite budgeting facts for a personal-finance app in India into a short, warm, "
    "plain-English explanation (at most 120 words, 2 short paragraphs or a few bullets). "
    "Rules: use ONLY the facts given. Copy every number and ₹ amount exactly as written; "
    "never calculate, round, convert or add new numbers, percentages or dates. Don't "
    "recommend specific funds or stocks. Don't add a disclaimer; the app shows one."
)


def _numbers(text: str) -> set[str]:
    return {m.replace(",", "").rstrip(".") for m in _NUMBER_RE.findall(text)}


def numbers_are_preserved(source: str, output: str) -> bool:
    """True if every number in `output` also appears in `source`."""
    return _numbers(output) <= _numbers(source)


def llm_enabled() -> bool:
    return settings.budget_explainer_provider == "anthropic"


async def explain(facts: list[str]) -> dict:
    """Return {"text", "source"}; source is "template" or "llm"."""
    template = " ".join(f for f in facts if f)
    if not llm_enabled() or not template:
        return {"text": template, "source": "template"}
    try:
        text = await _ask_claude(template)
    except Exception:  # any SDK/network/config failure -> template
        logger.warning("Budget explainer LLM call failed; using template text", exc_info=True)
        return {"text": template, "source": "template"}
    if not text or not numbers_are_preserved(template, text):
        logger.warning("Budget explainer output changed numbers; using template text")
        return {"text": template, "source": "template"}
    return {"text": text, "source": "llm"}


async def _ask_claude(facts: str) -> str | None:
    import anthropic  # optional dependency: `pip install anthropic`

    client = anthropic.AsyncAnthropic(timeout=30.0, max_retries=1)
    response = await client.beta.messages.create(
        model=settings.budget_explainer_model,
        max_tokens=2000,
        system=_SYSTEM_PROMPT,
        output_config={"effort": "low"},
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
        messages=[{"role": "user", "content": f"Facts:\n{facts}"}],
    )
    if response.stop_reason == "refusal":
        return None
    return "".join(b.text for b in response.content if b.type == "text").strip() or None
