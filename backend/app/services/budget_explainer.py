"""Optional friendly wording for the budget engine's output (Phase 8).

The rules engine and goal planner produce every number, flag and
recommendation, plus template sentences. This layer may only REPHRASE
those sentences:

- provider "template" (default): returns the engine's own sentences.
- provider "groq" or "gemini": asks an LLM with a free tier to rewrite them in
  plain, friendly language, through its OpenAI-compatible API. The reply is rejected (template used instead) if it contains
  any number that wasn't in the input, so the LLM can't invent or alter
  figures. Any error or missing key also falls back to the template.

The LLM is never used for categorisation or for any decision.
"""

import logging
import re
from dataclasses import dataclass

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Provider:
    base_url: str
    default_model: str
    key_setting: str


PROVIDERS = {
    # Preferred: Groq says it doesn't retain inference data by default, while
    # Gemini's free tier uses content to improve Google's products.
    "groq": Provider("https://api.groq.com/openai/v1", "openai/gpt-oss-120b", "groq_api_key"),
    "gemini": Provider(
        "https://generativelanguage.googleapis.com/v1beta/openai", "gemini-3.5-flash-lite", "gemini_api_key"
    ),
}

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
    "recommend specific funds or stocks. Don't add a disclaimer."
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
    return _api_key() is not None


def _api_key() -> str | None:
    provider = PROVIDERS.get(settings.budget_explainer_provider)
    key = getattr(settings, provider.key_setting) if provider else None
    return (key.get_secret_value().strip() or None) if key else None


async def explain(facts: list[str], system_prompt: str | None = None) -> dict:
    """Return {"text", "source"}; source is "template" or "llm".

    `system_prompt` replaces the budgeting instructions for other callers
    (the Phase 9 advisor); the number check is the same either way."""
    template = " ".join(f for f in facts if f)
    if not llm_enabled() or not template:
        return {"text": template, "source": "template"}
    try:
        text = await _ask_llm(template, system_prompt=system_prompt or _SYSTEM_PROMPT)
    except Exception:  # any network/config/format failure -> template
        logger.warning("Budget explainer LLM call failed; using template text", exc_info=True)
        return {"text": template, "source": "template"}
    if not text or not numbers_are_preserved(template, text):
        logger.warning("Budget explainer output changed numbers; using template text")
        return {"text": template, "source": "template"}
    return {"text": text, "source": "llm"}


async def _ask_llm(facts: str, system_prompt: str = _SYSTEM_PROMPT) -> str | None:
    provider = PROVIDERS[settings.budget_explainer_provider]
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            f"{provider.base_url}/chat/completions",
            headers={"Authorization": f"Bearer {_api_key()}"},
            json={
                "model": settings.budget_explainer_model or provider.default_model,
                "max_tokens": 2000,
                "reasoning_effort": "low",
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"Facts:\n{facts}"},
                ],
            },
        )
    response.raise_for_status()
    choice = response.json()["choices"][0]
    if choice.get("finish_reason") != "stop":  # cut off or filtered
        return None
    return (choice["message"].get("content") or "").strip() or None
