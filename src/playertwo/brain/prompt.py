"""Builds what the model sees from the active profile."""

from typing import Any

from playertwo.actions import GameProfile

FRAME_PROMPT = "This is the current screenshot. Choose the next action."
REASON_MAX_CHARS = 80
"""Caps the reason so a chatty model can't run out of reply tokens mid-JSON."""


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
        f'{{"action": {names}, "reason": "<at most 8 words>"}}'
    )


def decision_schema(profile: GameProfile) -> dict[str, Any]:
    """JSON schema for a reply. Ollama constrains decoding to it, so the model can only
    produce one of the profile's action names. Replies are still validated afterwards."""
    return {
        "type": "object",
        "properties": {
            "action": {"type": "string", "enum": profile.action_names},
            "reason": {"type": "string", "maxLength": REASON_MAX_CHARS},
        },
        "required": ["action", "reason"],
    }
