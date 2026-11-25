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

# The ₹ and % signs are part of the token, so "₹30" can't become "30%".
_NUMBER_RE = re.compile(r"₹?\d[\d,]*(?:\.\d+)?%?")
# Numbers written as words. A bare "one" is ordinary English ("no one"), so it
# only counts before a unit.
_NUMBER_WORD_RE = re.compile(
    r"\b(?:two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|fourteen|fifteen|"
    r"sixteen|seventeen|eighteen|nineteen|twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety|"
    r"hundred|thousand|lakhs?|crores?|million|half|quarter|double|triple|twice|"
    r"one(?=\s+(?:month|year|lakh|crore|percent|thousand|hundred)))\b",
    re.IGNORECASE,
)

_SYSTEM_PROMPT = (
    "You rewrite budgeting facts for a personal-finance app in India into a short, warm, "
    "plain-English explanation (at most 120 words, 2 short paragraphs or a few bullets). "
    "Rules: use ONLY the facts given. Copy every number and ₹ amount exactly as written; "
    "never calculate, round, convert or add new numbers, percentages or dates. Write numbers as "
    "digits, never words, and keep them in the order they appear in the facts. Don't "
    "recommend specific funds or stocks. Don't add a disclaimer; the app shows one."
)


def _numbers(text: str) -> list[str]:
    return [m.replace(",", "") for m in _NUMBER_RE.findall(text)]


def numbers_are_preserved(source: str, output: str) -> bool:
    """True if `output` only uses numbers from `source`, in the same order
    (so swapped figures fail), and adds no number words. Deliberately strict:
    a false alarm only means the template text is shown."""
    remaining = iter(_numbers(source))
    if not all(n in remaining for n in _numbers(output)):
        return False
    words = {w.lower() for w in _NUMBER_WORD_RE.findall(source)}
    return all(w.lower() in words for w in _NUMBER_WORD_RE.findall(output))


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

    key = settings.anthropic_api_key
    client = anthropic.AsyncAnthropic(
        # None lets the SDK use its own environment lookup.
        api_key=key.get_secret_value() if key and key.get_secret_value() else None,
        timeout=30.0,
        max_retries=1,
    )
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
