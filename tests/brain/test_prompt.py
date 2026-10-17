from playertwo.actions import GameProfile, History, PastAction
from playertwo.brain import (
    FRAME_PROMPT,
    REASON_MAX_CHARS,
    build_frame_prompt,
    build_system_prompt,
    decision_schema,
)


def test_prompt_lists_every_profile_action_and_the_goal(profile: GameProfile) -> None:
    prompt = build_system_prompt(profile)
    assert profile.goal in prompt
    for name in profile.action_names:
        assert f'"{name}"' in prompt


def test_schema_only_allows_profile_actions(profile: GameProfile) -> None:
    schema = decision_schema(profile)
    assert schema["properties"]["action"]["enum"] == profile.action_names
    assert set(schema["required"]) == {"action", "reason"}


def test_schema_caps_reason_length(profile: GameProfile) -> None:
    # Regression: uncapped reasons ran past num_predict and truncated the JSON (6/10
    # replies unparseable in the first benchmark).
    assert decision_schema(profile)["properties"]["reason"]["maxLength"] == REASON_MAX_CHARS


def test_prompt_uses_the_profile_game_type(profile: GameProfile) -> None:
    assert "a third-person video game" in build_system_prompt(profile)
    racer = profile.model_copy(update={"game_type": "top-down racing game"})
    assert "You control a character in a top-down racing game" in build_system_prompt(racer)


def test_frame_prompt_without_history_is_just_the_ask() -> None:
    assert build_frame_prompt(None) == FRAME_PROMPT
    assert build_frame_prompt(History()) == FRAME_PROMPT


def test_frame_prompt_lists_recent_actions_with_their_effect_but_not_reasons() -> None:
    # Regression: with its own reasons in the history, the 2B model copied them and kept
    # turning with the target straight ahead (level 1: 1/19 with memory, 20/20 without).
    history = History(
        (
            PastAction("turn_left", "positioned in front of a wall", True),
            PastAction("move_forward", "", False),
            PastAction("wait", "nothing to do", None),
        )
    )
    prompt = build_frame_prompt(history)
    assert prompt.splitlines() == [
        "Your last actions, oldest first:",
        "- turn_left -> screen changed",
        "- move_forward -> NO change",
        "- wait",
        FRAME_PROMPT,
    ]
    assert "wall" not in prompt


def test_frame_prompt_warns_when_stuck() -> None:
    history = History(
        (PastAction("move_forward", "go", False),) * 3, stuck_action="move_forward", stuck_repeats=3
    )
    prompt = build_frame_prompt(history)
    assert "move_forward did nothing 3 times in a row" in prompt
    assert "Choose a different action" in prompt
    assert prompt.endswith(FRAME_PROMPT)


def test_frame_prompt_stays_short_with_a_full_memory() -> None:
    # Small models degrade with long context: a full memory stays well under 500
    # characters (roughly 120 tokens).
    entry = PastAction("move_forward", "x" * 40, False)
    history = History((entry,) * 8, stuck_action="move_forward", stuck_repeats=8)
    assert len(build_frame_prompt(history)) < 500


def test_steering_only_actions_are_not_offered_to_the_model() -> None:
    from pathlib import Path

    testbed = GameProfile.load(Path(__file__).resolve().parents[2] / "profiles" / "testbed.yaml")
    prompt = build_system_prompt(testbed)
    assert "nudge_left" not in prompt and "nudge_right" not in prompt
    enum = decision_schema(testbed)["properties"]["action"]["enum"]
    assert enum == ["move_forward", "turn_left", "turn_right", "wait"]
