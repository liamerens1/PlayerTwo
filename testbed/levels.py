"""The five levels. Each layout is generated from (level, seed), so runs are repeatable."""

import math
import random
from dataclasses import dataclass

from testbed.autopilot import plan_path
from testbed.world import Layout, Rect

TARGET_SIZE = 2.5
WALL_HEIGHT = 2.0
LEVEL_4_ATTEMPTS = 200
"""Level 4 layouts are re-rolled (same seed, next random numbers) until one is winnable."""


@dataclass(frozen=True)
class LevelInfo:
    name: str
    timeout_seconds: float


LEVELS: dict[int, LevelInfo] = {
    1: LevelInfo("Open field, target straight ahead", 30.0),
    2: LevelInfo("Target at a random angle, often off-screen", 40.0),
    3: LevelInfo("A wall between you and the target", 60.0),
    4: LevelInfo("Several obstacles", 60.0),
    5: LevelInfo("A pit: falling is a death", 60.0),
}


def generate_layout(level: int, seed: int, timeout_seconds: float | None = None) -> Layout:
    """The layout for one episode. Same (level, seed) always gives the same layout."""
    if level not in LEVELS:
        raise ValueError(f"level must be one of {sorted(LEVELS)}, got {level}")
    rng = random.Random(f"playertwo-testbed:{level}:{seed}")
    timeout = timeout_seconds if timeout_seconds is not None else LEVELS[level].timeout_seconds
    match level:
        case 1:
            return _open_field(rng, seed, timeout)
        case 2:
            return _random_angle(rng, seed, timeout)
        case 3:
            return _wall(rng, seed, timeout)
        case 4:
            return _obstacles(rng, seed, timeout)
        case _:
            return _pit(rng, seed, timeout)


def _target(x: float, z: float) -> Rect:
    return Rect.around(x, z, TARGET_SIZE, TARGET_SIZE)


def _layout(
    level: int,
    seed: int,
    timeout: float,
    target: Rect,
    platform: Rect,
    *,
    obstacles: tuple[Rect, ...] = (),
    fenced: bool = True,
    pit: Rect | None = None,
) -> Layout:
    return Layout(
        level=level,
        seed=seed,
        start=(0.0, 0.0),
        start_heading=0.0,
        target=target,
        obstacles=obstacles,
        obstacle_height=WALL_HEIGHT,
        platform=platform,
        fenced=fenced,
        pit=pit,
        timeout_seconds=timeout,
    )


def _open_field(rng: random.Random, seed: int, timeout: float) -> Layout:
    target = _target(rng.uniform(-1.0, 1.0), rng.uniform(10.0, 14.0))
    return _layout(1, seed, timeout, target, Rect(-15.0, -8.0, 15.0, 30.0))


def _random_angle(rng: random.Random, seed: int, timeout: float) -> Layout:
    angle = math.radians(rng.uniform(-180.0, 180.0))
    distance = rng.uniform(9.0, 13.0)
    target = _target(distance * math.sin(angle), distance * math.cos(angle))
    return _layout(2, seed, timeout, target, Rect(-20.0, -20.0, 20.0, 20.0))


def _wall(rng: random.Random, seed: int, timeout: float) -> Layout:
    target_z = rng.uniform(15.0, 18.0)
    target = _target(rng.uniform(-2.0, 2.0), target_z)
    wall = Rect.around(rng.uniform(-2.5, 2.5), target_z / 2, rng.uniform(9.0, 12.0), 1.0)
    return _layout(3, seed, timeout, target, Rect(-15.0, -8.0, 15.0, 30.0), obstacles=(wall,))


def _obstacles(rng: random.Random, seed: int, timeout: float) -> Layout:
    platform = Rect(-15.0, -8.0, 15.0, 30.0)
    for _ in range(LEVEL_4_ATTEMPTS):
        tx, tz = rng.uniform(-4.0, 4.0), rng.uniform(16.0, 20.0)
        target = _target(tx, tz)
        keep_clear = [Rect.around(0.0, 0.0, 5.0, 5.0), target.expanded(1.5)]
        # The first box sits on the straight line to the target, so walking straight fails.
        fraction = rng.uniform(0.4, 0.6)
        boxes = [Rect.around(tx * fraction, tz * fraction, 3.0, 3.0)]
        for _ in range(rng.randint(4, 6)):
            for _ in range(50):
                size = rng.uniform(2.0, 3.5)
                box = Rect.around(rng.uniform(-10.0, 10.0), rng.uniform(3.0, tz - 2.0), size, size)
                # 0.8 on each side leaves a 1.6 gap, wider than the player.
                if not any(box.overlaps(other.expanded(0.8)) for other in boxes + keep_clear):
                    boxes.append(box)
                    break
        layout = _layout(4, seed, timeout, target, platform, obstacles=tuple(boxes))
        if plan_path(layout) is not None:
            return layout
    raise RuntimeError(f"no winnable level-4 layout for seed {seed}")  # pragma: no cover


def _pit(rng: random.Random, seed: int, timeout: float) -> Layout:
    target_z = rng.uniform(15.0, 18.0)
    target = _target(rng.uniform(-2.0, 2.0), target_z)
    pit = Rect.around(
        rng.uniform(-1.5, 1.5), rng.uniform(6.5, 8.5), rng.uniform(7.0, 9.0), rng.uniform(3.5, 5.0)
    )
    platform = Rect(-9.0, -6.0, 9.0, 26.0)
    return _layout(5, seed, timeout, target, platform, fenced=False, pit=pit)
