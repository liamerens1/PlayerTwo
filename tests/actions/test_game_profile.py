import pytest
from pydantic import ValidationError

from playertwo.actions import Decision, GameProfile, HoldAction


def test_starter_profile_loads(profile: GameProfile) -> None:
    assert profile.name == "simple-walker"
    assert "wait" in profile.action_names
    assert isinstance(profile.actions["move_forward"], HoldAction)


def test_profile_without_wait_is_rejected() -> None:
    with pytest.raises(ValidationError):
        GameProfile.model_validate(
            {"name": "x", "goal": "y", "actions": {"jump": {"type": "press", "key": "space"}}}
        )


def test_unknown_action_type_is_rejected() -> None:
    with pytest.raises(ValidationError):
        GameProfile.model_validate(
            {
                "name": "x",
                "goal": "y",
                "actions": {"wait": {"type": "wait"}, "fly": {"type": "teleport"}},
            }
        )


def test_unknown_decision_becomes_wait(profile: GameProfile) -> None:
    decision = Decision(action="self_destruct").validated_against(profile)
    assert decision.action == "wait"


def test_known_decision_passes_through(profile: GameProfile) -> None:
    decision = Decision(action="interact", reason="door").validated_against(profile)
    assert decision.action == "interact"
