import pytest

from testbed.autopilot import Autopilot
from testbed.episode import Episode, Outcome
from testbed.levels import LEVELS, generate_layout
from testbed.physics import MOVE_SPEED, PLAYER_RADIUS, PlayerState, start_state, step
from testbed.world import Layout, Rect

DT = 1 / 30


def _layout(**changes: object) -> Layout:
    base = {
        "level": 1,
        "seed": 1,
        "start": (0.0, 0.0),
        "start_heading": 0.0,
        "target": Rect.around(0, 20, 2.5, 2.5),
        "obstacles": (),
        "obstacle_height": 2.0,
        "platform": Rect(-10, -10, 10, 30),
        "fenced": True,
        "pit": None,
        "timeout_seconds": 10.0,
    }
    base.update(changes)
    return Layout(**base)  # type: ignore[arg-type]


def _walk(layout: Layout, state: PlayerState, seconds: float, **kw: float) -> PlayerState:
    for _ in range(round(seconds / DT)):
        state = step(layout, state, kw.get("forward", 1.0), kw.get("strafe", 0.0), 0.0, DT)
    return state


def test_forward_moves_along_the_heading() -> None:
    layout = _layout()
    state = _walk(layout, PlayerState(0, 0, 0), 1.0)
    assert state.z == pytest.approx(MOVE_SPEED) and state.x == pytest.approx(0)
    state = _walk(layout, PlayerState(0, 0, 90), 1.0)
    assert state.x == pytest.approx(MOVE_SPEED) and state.z == pytest.approx(0)


def test_strafe_right_is_to_the_right_of_the_heading() -> None:
    state = _walk(_layout(), PlayerState(0, 0, 0), 0.5, forward=0, strafe=1)
    assert state.x > 0 and state.z == pytest.approx(0)


def test_turning_wraps() -> None:
    state = step(_layout(), PlayerState(0, 0, 170), 0, 0, 30, DT)
    assert state.heading == pytest.approx(-160)


def test_walls_block_and_the_player_slides_along_them() -> None:
    wall = Rect(-5, 3, 5, 4)
    layout = _layout(obstacles=(wall,))
    state = _walk(layout, PlayerState(0, 0, 0), 2.0)
    assert state.z == pytest.approx(3 - PLAYER_RADIUS, abs=0.2)
    slid = _walk(layout, PlayerState(0, 0, 45), 2.0)
    assert slid.x > 3 and slid.z < 3


def test_a_huge_frame_cannot_tunnel_through_a_wall() -> None:
    layout = _layout(obstacles=(Rect(-5, 3, 5, 4),))
    assert step(layout, PlayerState(0, 0, 0), 1, 0, 0, 5.0).z < 3


def test_fence_keeps_the_player_on_the_platform() -> None:
    layout = _layout(platform=Rect(-5, -5, 5, 5), target=Rect.around(0, 50, 1, 1))
    state = _walk(layout, PlayerState(0, 0, 0), 5.0)
    assert state.z == pytest.approx(5 - PLAYER_RADIUS)


def test_success_on_touching_the_target() -> None:
    layout = _layout(target=Rect.around(0, 4, 2.5, 2.5))
    episode = Episode(layout)
    state = PlayerState(0, 0, 0)
    outcome = None
    while outcome is None:
        state = step(layout, state, 1, 0, 0, DT)
        outcome = episode.update(state, DT)
    assert outcome is Outcome.SUCCESS
    assert episode.elapsed == pytest.approx((4 - 1.25 - PLAYER_RADIUS) / MOVE_SPEED, abs=0.05)
    result = episode.result(episode=3, tag="memory-on")
    assert result.outcome is Outcome.SUCCESS and result.episode == 3 and result.tag == "memory-on"
    assert result.closest_distance == pytest.approx(1.75, abs=0.15)


def test_falling_into_the_pit_is_a_death() -> None:
    layout = _layout(fenced=False, pit=Rect(-3, 2, 3, 5))
    episode = Episode(layout)
    state = PlayerState(0, 0, 0)
    outcome = None
    for _ in range(60):
        state = step(layout, state, 1, 0, 0, DT)
        if (outcome := episode.update(state, DT)) is not None:
            break
    assert outcome is Outcome.FELL


def test_walking_off_an_unfenced_edge_is_a_death() -> None:
    layout = _layout(fenced=False, platform=Rect(-2, -2, 2, 30))
    episode = Episode(layout)
    state = _walk(layout, PlayerState(0, 0, 90), 1.0)
    assert episode.update(state, DT) is Outcome.FELL


def test_timeout() -> None:
    episode = Episode(_layout(timeout_seconds=1.0))
    state = PlayerState(0, 0, 0)
    outcomes = [episode.update(state, 0.25) for _ in range(5)]
    assert outcomes == [None, None, None, Outcome.TIMEOUT, None]  # reported once
    assert episode.result().outcome is Outcome.TIMEOUT


def test_closest_distance_is_tracked() -> None:
    layout = _layout()
    episode = Episode(layout)
    assert episode.closest == pytest.approx(20)
    episode.update(PlayerState(0, 12, 0), DT)
    episode.update(PlayerState(0, 2, 0), DT)
    assert episode.closest == pytest.approx(8)


def test_result_before_the_end_is_an_error() -> None:
    with pytest.raises(RuntimeError):
        Episode(_layout()).result()


@pytest.mark.parametrize("level", sorted(LEVELS))
def test_autopilot_wins_every_level(level: int) -> None:
    """The levels are winnable with the game's own movement rules, well inside the time."""
    for seed in range(1, 21):
        layout = generate_layout(level, seed)
        pilot = Autopilot(layout)
        episode = Episode(layout)
        state = start_state(layout)
        outcome = None
        while outcome is None:
            command = pilot.command(state, DT)
            state = step(layout, state, command.forward, 0, command.turn_degrees, DT)
            outcome = episode.update(state, DT)
        assert outcome is Outcome.SUCCESS, f"level {level} seed {seed}: {outcome}"
        assert episode.elapsed < layout.timeout_seconds / 2
