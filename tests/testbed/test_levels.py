import math

import pytest

from testbed.autopilot import plan_path
from testbed.levels import LEVELS, generate_layout
from testbed.physics import PLAYER_RADIUS, blocked, falling, start_state
from testbed.world import Rect, ground_tiles, heading_towards, wrap_degrees

SEEDS = range(1, 41)
HALF_VIEW_DEGREES = 45
"""About half the camera's horizontal field of view."""


@pytest.mark.parametrize("level", sorted(LEVELS))
def test_same_seed_same_layout(level: int) -> None:
    assert generate_layout(level, 7) == generate_layout(level, 7)
    assert generate_layout(level, 7) != generate_layout(level, 8)


def test_unknown_level_is_rejected() -> None:
    with pytest.raises(ValueError, match="level must be one of"):
        generate_layout(6, 1)


def test_timeout_override() -> None:
    assert generate_layout(1, 1).timeout_seconds == LEVELS[1].timeout_seconds
    assert generate_layout(1, 1, timeout_seconds=5).timeout_seconds == 5


@pytest.mark.parametrize("level", sorted(LEVELS))
def test_every_layout_starts_safe_and_is_winnable(level: int) -> None:
    for seed in SEEDS:
        layout = generate_layout(level, seed)
        state = start_state(layout)
        assert not blocked(layout, state.x, state.z), seed
        assert not falling(layout, state), seed
        assert layout.platform.contains(*layout.target.center), seed
        assert not any(box.overlaps(layout.target) for box in layout.obstacles), seed
        assert plan_path(layout) is not None, f"level {level} seed {seed} has no path"


def test_level_1_target_is_straight_ahead() -> None:
    for seed in SEEDS:
        layout = generate_layout(1, seed)
        x, z = layout.target.center
        assert abs(heading_towards(0, 0, x, z)) < 10 and z > 8


def test_level_2_target_is_often_off_screen() -> None:
    off_screen = 0
    for seed in SEEDS:
        x, z = generate_layout(2, seed).target.center
        off_screen += abs(heading_towards(0, 0, x, z)) > HALF_VIEW_DEGREES
    assert off_screen / len(SEEDS) > 0.5


def test_level_3_wall_blocks_the_straight_line() -> None:
    for seed in SEEDS:
        layout = generate_layout(3, seed)
        (wall,) = layout.obstacles
        tx, tz = layout.target.center
        steps = [(tx * t / 100, tz * t / 100) for t in range(101)]
        assert any(wall.expanded(PLAYER_RADIUS).contains(x, z) for x, z in steps), seed


def test_level_4_has_several_obstacles_one_in_the_way() -> None:
    for seed in SEEDS:
        layout = generate_layout(4, seed)
        assert len(layout.obstacles) >= 4
        tx, tz = layout.target.center
        steps = [(tx * t / 100, tz * t / 100) for t in range(101)]
        assert any(blocked(layout, x, z) for x, z in steps), seed


def test_level_5_has_a_pit_in_the_way_and_no_fence() -> None:
    for seed in SEEDS:
        layout = generate_layout(5, seed)
        assert layout.pit is not None and not layout.fenced
        tx, tz = layout.target.center
        steps = [(tx * t / 100, tz * t / 100) for t in range(101)]
        assert any(layout.pit.contains(x, z) for x, z in steps), seed


def test_ground_tiles_cover_the_platform_except_the_pit() -> None:
    platform = Rect(-9, -6, 9, 26)
    pit = Rect(-3, 5, 4, 9)
    tiles = ground_tiles(platform, pit)
    assert math.isclose(sum(t.area for t in tiles), platform.area - pit.area)
    assert not any(t.overlaps(pit) for t in tiles)
    assert ground_tiles(platform, None) == [platform]


def test_wrap_degrees() -> None:
    assert wrap_degrees(190) == -170
    assert wrap_degrees(-190) == 170
    assert wrap_degrees(180) == 180
    assert wrap_degrees(-180) == 180
    assert wrap_degrees(720 + 30) == 30
