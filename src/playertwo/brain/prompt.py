"""Builds what the model sees from the active profile."""

from typing import Any

from playertwo.actions import GameProfile, History, SteerTarget

FRAME_PROMPT = "This is the current screenshot. Choose the next action."
REASON_MAX_CHARS = 80
"""Caps the reason so a chatty model can't run out of reply tokens mid-JSON."""


def build_system_prompt(profile: GameProfile) -> str:
    """The model only ever sees the actions the active profile allows."""
    action_lines = "\n".join(
        f"- {name}: {spec.description or spec.type}"
        for name, spec in profile.actions.items()
        if spec.for_model
    )
    names = " | ".join(f'"{name}"' for name in profile.model_action_names)
    return (
        f"You control a character in a {profile.game_type} by looking at screenshots.\n"
        f"Goal: {profile.goal}\n\n"
        f"Available actions:\n{action_lines}\n\n"
        "Reply with ONE action as JSON only, no other text:\n"
        f'{{"action": {names}, "reason": "<at most 8 words>"}}'
    )


def build_frame_prompt(history: History | None = None) -> str:
    """The per-frame prompt: the model's recent actions (Tier 1 memory), then the ask.

    One short line per action, since small models get worse with long context. The
    model's own past reasons are deliberately left out: qwen3-vl 2B copied them word for
    word ("positioned in front of a wall") and repeated the old action with the target
    straight ahead. Level 1 went from 20/20 without memory to 1/19 with reasons in the
    history; with action and effect only it kept walking at the target (offline check).
    """
    if history is None or not history.recent:
        return FRAME_PROMPT
    lines = ["Your last actions, oldest first:"]
    for past in history.recent:
        if past.screen_changed is None:
            result = ""
        else:
            result = " -> screen changed" if past.screen_changed else " -> NO change"
        lines.append(f"- {past.action}{result}")
    if history.stuck_action is not None:
        lines.append(
            f"{history.stuck_action} did nothing {history.stuck_repeats} times in a row: "
            "you are probably stuck. Choose a different action."
        )
    lines.append(FRAME_PROMPT)
    return "\n".join(lines)


def decision_schema(profile: GameProfile) -> dict[str, Any]:
    """JSON schema for a reply. Ollama constrains decoding to it, so the model can only
    produce one of the profile's action names. Replies are still validated afterwards."""
    return {
        "type": "object",
        "properties": {
            "action": {"type": "string", "enum": profile.model_action_names},
            "reason": {"type": "string", "maxLength": REASON_MAX_CHARS},
        },
        "required": ["action", "reason"],
    }


def build_locate_prompt(target: SteerTarget) -> str:
    """Look, then steer: ask only where the target is. Chosen by the Phase 6 perception
    test: a box in a fixed JSON shape beat asking "left, centre or right" (which made the
    2B see targets that weren't there) and a free-form box (it boxed the player instead
    when the target was off-screen)."""
    return (
        f"Is {target.description} visible in this image? "
        "If yes, give its bounding box [x1, y1, x2, y2]."
    )


def locate_schema() -> dict[str, Any]:
    """JSON schema for a locate reply: visible, plus a 4-number box."""
    return {
        "type": "object",
        "properties": {
            "visible": {"type": "boolean"},
            "box": {"type": "array", "items": {"type": "number"}, "minItems": 4, "maxItems": 4},
        },
        "required": ["visible", "box"],
    }
