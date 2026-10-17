import pytest
from pydantic import ValidationError

from playertwo.actions import GameProfile, Sighting, SteerTarget
from playertwo.steering import Steerer

TARGET = SteerTarget(
    description="the yellow cube",
    forward="move_forward",
    turn_left="turn_left",
    turn_right="turn_right",
    centre_width=0.34,
    search="left",
)


def _seen(x: float) -> Sighting:
    return Sighting(visible=True, x=x, box=(x - 0.05, 0.3, x + 0.05, 0.5))


NOT_SEEN = Sighting(visible=False)


@pytest.mark.parametrize(
    ("x", "action"),
    [
        (0.10, "turn_left"),
        (0.32, "turn_left"),  # just outside the band (0.33-0.67)
        (0.34, "move_forward"),
        (0.50, "move_forward"),
        (0.66, "move_forward"),
        (0.68, "turn_right"),
        (0.95, "turn_right"),
    ],
)
def test_turns_towards_the_target_and_walks_when_centred(x: float, action: str) -> None:
    assert Steerer(TARGET).decide(_seen(x)).action == action


def test_searches_the_default_way_before_ever_seeing_it() -> None:
    assert Steerer(TARGET).decide(NOT_SEEN).action == "turn_left"
    right = TARGET.model_copy(update={"search": "right"})
    assert Steerer(right).decide(NOT_SEEN).action == "turn_right"


def test_a_lost_target_is_searched_for_on_the_side_it_was_last_seen() -> None:
    # The fix for level 2: the model used to keep turning the wrong way.
    steerer = Steerer(TARGET)
    steerer.decide(_seen(0.9))  # seen on the right
    assert steerer.decide(NOT_SEEN).action == "turn_right"
    steerer.decide(_seen(0.1))  # then on the left
    assert steerer.decide(NOT_SEEN).action == "turn_left"


def test_a_centred_target_remembers_which_half_it_was_in() -> None:
    steerer = Steerer(TARGET)
    steerer.decide(_seen(0.6))
    assert steerer.decide(NOT_SEEN).action == "turn_right"


def test_a_failed_locate_waits_instead_of_turning() -> None:
    decision = Steerer(TARGET).decide(None)
    assert decision.action == "wait"


def test_reasons_say_what_steering_saw() -> None:
    steerer = Steerer(TARGET)
    assert steerer.decide(_seen(0.8)).reason == "target right (x=0.80)"
    assert steerer.decide(NOT_SEEN).reason == "searching right"


# --- the profile's target section -------------------------------------------------


def _profile(target: dict[str, object] | None) -> GameProfile:
    data: dict[str, object] = {
        "name": "t",
        "goal": "g",
        "actions": {
            "move_forward": {"type": "hold", "key": "w", "seconds": 0.8},
            "turn_left": {"type": "mouse", "dx": -150},
            "turn_right": {"type": "mouse", "dx": 150},
            "wait": {"type": "wait"},
        },
    }
    if target is not None:
        data["target"] = target
    return GameProfile.model_validate(data)


GOOD = {
    "description": "the yellow cube",
    "forward": "move_forward",
    "turn_left": "turn_left",
    "turn_right": "turn_right",
}


def test_profiles_without_a_target_still_load() -> None:
    assert _profile(None).target is None


def test_target_must_use_the_profiles_actions() -> None:
    assert _profile(GOOD).target == SteerTarget(**GOOD)  # type: ignore[arg-type]
    with pytest.raises(ValidationError, match=r"target.turn_left is 'spin'"):
        _profile({**GOOD, "turn_left": "spin"})


def test_target_actions_must_be_different() -> None:
    with pytest.raises(ValidationError, match="must all be different"):
        _profile({**GOOD, "turn_right": "turn_left"})


def test_centre_width_is_a_fraction() -> None:
    with pytest.raises(ValidationError):
        _profile({**GOOD, "centre_width": 1.5})


# --- nudges and overshoot ----------------------------------------------------------

NUDGING = TARGET.model_copy(
    update={
        "nudge_left": "nudge_left",
        "nudge_right": "nudge_right",
        "centre_width": 0.2,
        "nudge_zone": 0.3,
    }
)


@pytest.mark.parametrize(
    ("x", "action"),
    [
        (0.05, "turn_left"),  # far off: a full turn
        (0.25, "nudge_left"),  # within 0.3 of the centre: a nudge
        (0.45, "move_forward"),  # in the 0.4-0.6 band
        (0.72, "nudge_right"),
        (0.85, "turn_right"),
    ],
)
def test_nudges_near_the_centre_full_turns_far_off(x: float, action: str) -> None:
    assert Steerer(NUDGING).decide(_seen(x)).action == action


def test_an_overshoot_gets_a_nudge_not_another_full_turn() -> None:
    # Seen on the testbed: a 30-degree turn swung the cube from far left to far right and
    # back, forever. After a turn one way, a target now on the other side gets a nudge.
    steerer = Steerer(NUDGING)
    assert steerer.decide(_seen(0.05)).action == "turn_left"
    decision = steerer.decide(_seen(0.95))
    assert decision.action == "nudge_right"
    assert decision.reason is not None and decision.reason.startswith("overshot")
    # Still off to the right after the nudge: no overshoot now, so a full turn again.
    assert steerer.decide(_seen(0.95)).action == "turn_right"


def test_without_nudges_steering_is_unchanged() -> None:
    steerer = Steerer(TARGET)
    steerer.decide(_seen(0.05))
    assert steerer.decide(_seen(0.95)).action == "turn_right"


def test_nudges_must_come_in_pairs() -> None:
    with pytest.raises(ValidationError, match="go together"):
        _profile({**GOOD, "nudge_left": "turn_left"})


# --- detours ------------------------------------------------------------------------

DETOURING = NUDGING.model_copy(
    update={"sidestep_left": "strafe_left", "sidestep_right": "strafe_right", "detour_steps": 3}
)


def test_stuck_starts_a_sidestep_detour_towards_the_target_side() -> None:
    # Seen on level 3: walking at a cube behind a wall, the model's one-off turn was
    # undone by steering at once. A detour strafes several steps, still facing the cube.
    steerer = Steerer(DETOURING)
    steerer.decide(_seen(0.58))  # centred, right half
    assert steerer.needs_look(stuck=True) is False
    actions = [steerer.decide(_seen(0.58), stuck=True).action for _ in range(3)]
    assert actions == ["strafe_right"] * 3
    # Detour done: steering as usual again.
    assert steerer.needs_look(stuck=False)
    assert steerer.decide(_seen(0.58)).action == "move_forward"


def test_a_detour_finishes_even_if_no_longer_stuck() -> None:
    steerer = Steerer(DETOURING)
    steerer.decide(_seen(0.45))  # left half
    assert steerer.decide(_seen(0.45), stuck=True).action == "strafe_left"
    assert not steerer.needs_look(stuck=False)  # two more to go, no need to look
    assert steerer.decide(None).action == "strafe_left"
    assert steerer.decide(None).action == "strafe_left"
    assert steerer.decide(_seen(0.45)).action == "move_forward"


def test_blocked_again_keeps_going_the_same_way() -> None:
    steerer = Steerer(DETOURING)
    steerer.decide(_seen(0.58))
    for _ in range(3):
        steerer.decide(_seen(0.58), stuck=True)
    steerer.decide(_seen(0.42))  # now slightly left of centre, still blocked
    assert steerer.decide(_seen(0.42), stuck=True).action == "strafe_right"


def test_without_sidesteps_stuck_is_left_to_the_model() -> None:
    steerer = Steerer(NUDGING)
    assert not steerer.can_detour
    assert steerer.needs_look(stuck=True)


def test_sidesteps_must_come_in_pairs() -> None:
    with pytest.raises(ValidationError, match="sidestep_left and sidestep_right go together"):
        _profile({**GOOD, "sidestep_left": "turn_left"})
