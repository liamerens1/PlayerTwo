from playertwo.actions import GameProfile
from playertwo.brain import REASON_MAX_CHARS, build_system_prompt, decision_schema


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
