"""Template summary of Phase 9 advice: the default text, and the only text
an optional LLM (step 4) may reword. Every number it contains comes from
an action's own title."""

from app.services import budget_explainer


def template_summary(result: dict) -> str:
    actions, setup = result["actions"], result["setup"]
    if not actions and setup:
        return f"To get personalised advice, start with: {setup[0]['title'].lower()}."
    if not actions:
        return "You're on track: nothing needs your attention right now."
    count = len(actions)
    text = f"{count} thing{'s' if count > 1 else ''} to look at, most important first. Start with: {actions[0]['title']}."
    if count > 1:
        text += f" Then: {actions[1]['title']}."
    if result["partial"]:
        text += " Some information couldn't be loaded, so this advice may be incomplete."
    return text


# --- Optional LLM rewording (step 4) ------------------------------------------------

# How many actions the LLM sees: enough for a summary, short enough to check.
LLM_ACTIONS = 3

ADVISOR_SYSTEM_PROMPT = (
    "You write a short summary of a personal-finance app's advice for a user in India: at most "
    "90 words, plain and warm, one short paragraph. Rules: use ONLY the numbered advice given, in "
    "the same order, most important first. Copy every number and ₹ amount exactly as written, as "
    "digits; never calculate, round, convert or add numbers, percentages or dates. Name only the "
    "stocks and funds already mentioned. Never add advice, never tell the user to buy or sell "
    "anything that isn't in the list, and don't add a disclaimer."
)


def llm_input(result: dict) -> list[str]:
    """The facts the LLM may reword: the top actions' own sentences."""
    lines = [f"{i}. {a['title']}. {a['detail']}" for i, a in enumerate(result["actions"][:LLM_ACTIONS], 1)]
    if result["partial"]:
        lines.append("Some information couldn't be loaded, so this advice may be incomplete.")
    return lines


async def summarize(result: dict) -> dict:
    """{"text", "source"}: the LLM's wording if it's enabled and keeps every
    number, else the template. Never raises."""
    template = template_summary(result)
    if not result["actions"] or not budget_explainer.llm_enabled():
        return {"text": template, "source": "template"}
    out = await budget_explainer.explain(llm_input(result), system_prompt=ADVISOR_SYSTEM_PROMPT)
    if out["source"] != "llm":  # rejected or failed: the short template, not the raw lines
        return {"text": template, "source": "template"}
    return out
