"""Builds the system prompt from the active profile."""

from playertwo.actions import GameProfile


def build_system_prompt(profile: GameProfile) -> str:
    """The model only ever sees the actions the active profile allows."""
    action_lines = "\n".join(
        f"- {name}: {spec.description or spec.type}" for name, spec in profile.actions.items()
    )
    names = " | ".join(f'"{name}"' for name in profile.action_names)
    return (
        "You control a character in a third-person video game by looking at screenshots.\n"
        f"Goal: {profile.goal}\n\n"
        f"Available actions:\n{action_lines}\n\n"
        "Reply with ONE action as JSON only, no other text:\n"
        f'{{"action": {names}, "reason": "<a few words>"}}'
    )
