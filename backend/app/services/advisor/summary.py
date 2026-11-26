"""Template summary of Phase 9 advice: the default text, and the only text
an optional LLM (step 4) may reword. Every number it contains comes from
an action's own title."""


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
