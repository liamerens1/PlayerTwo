from playertwo.actions import GameProfile
from playertwo.brain import build_system_prompt


def test_prompt_lists_every_profile_action_and_the_goal(profile: GameProfile) -> None:
    prompt = build_system_prompt(profile)
    assert profile.goal in prompt
    for name in profile.action_names:
        assert f'"{name}"' in prompt
