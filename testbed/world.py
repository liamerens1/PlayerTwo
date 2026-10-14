"""Shapes and layouts. Top-down coordinates: x to the right, z forward, in world units.

Headings are degrees clockwise from +z seen from above (0 = facing +z, 90 = facing +x),
which is also Ursina's `rotation_y`.
"""

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class Rect:
    """An axis-aligned rectangle on the ground plane."""

    min_x: float
    min_z: float
    max_x: float
    max_z: float

    @classmethod
    def around(cls, x: float, z: float, width: float, depth: float) -> "Rect":
        return cls(x - width / 2, z - depth / 2, x + width / 2, z + depth / 2)

    @property
    def width(self) -> float:
        return self.max_x - self.min_x

    @property
    def depth(self) -> float:
        return self.max_z - self.min_z

    @property
    def center(self) -> tuple[float, float]:
        return (self.min_x + self.max_x) / 2, (self.min_z + self.max_z) / 2

    @property
    def area(self) -> float:
        return max(0.0, self.width) * max(0.0, self.depth)

    def contains(self, x: float, z: float) -> bool:
        return self.min_x <= x <= self.max_x and self.min_z <= z <= self.max_z

    def expanded(self, margin: float) -> "Rect":
        """Grown by `margin` on every side (shrunk if negative)."""
        return Rect(
            self.min_x - margin, self.min_z - margin, self.max_x + margin, self.max_z + margin
        )

    def overlaps(self, other: "Rect") -> bool:
        return (
            self.min_x < other.max_x
            and other.min_x < self.max_x
            and self.min_z < other.max_z
            and other.min_z < self.max_z
        )


@dataclass(frozen=True)
class Layout:
    """Everything that defines one episode's world. Generated from (level, seed)."""

    level: int
    seed: int
    start: tuple[float, float]
    start_heading: float
    target: Rect
    obstacles: tuple[Rect, ...]
    obstacle_height: float
    platform: Rect
    """The walkable ground. Fenced levels keep the player on it; unfenced ones don't."""
    fenced: bool
    pit: Rect | None
    timeout_seconds: float

    def distance_to_target(self, x: float, z: float) -> float:
        """Centre-to-centre distance on the ground plane."""
        tx, tz = self.target.center
        return math.hypot(tx - x, tz - z)


def wrap_degrees(angle: float) -> float:
    """Into (-180, 180]."""
    wrapped = math.fmod(angle, 360.0)
    if wrapped <= -180.0:
        wrapped += 360.0
    elif wrapped > 180.0:
        wrapped -= 360.0
    return wrapped


def heading_towards(from_x: float, from_z: float, to_x: float, to_z: float) -> float:
    """Heading (degrees clockwise from +z) pointing from one point at another."""
    return math.degrees(math.atan2(to_x - from_x, to_z - from_z))


def ground_tiles(platform: Rect, pit: Rect | None) -> list[Rect]:
    """The platform as rectangles with the pit cut out, for drawing the ground."""
    if pit is None:
        return [platform]
    hole = Rect(
        max(pit.min_x, platform.min_x),
        max(pit.min_z, platform.min_z),
        min(pit.max_x, platform.max_x),
        min(pit.max_z, platform.max_z),
    )
    if hole.width <= 0 or hole.depth <= 0:
        return [platform]
    tiles = [
        Rect(platform.min_x, platform.min_z, platform.max_x, hole.min_z),  # near side
        Rect(platform.min_x, hole.max_z, platform.max_x, platform.max_z),  # far side
        Rect(platform.min_x, hole.min_z, hole.min_x, hole.max_z),  # left of the hole
        Rect(hole.max_x, hole.min_z, platform.max_x, hole.max_z),  # right of the hole
    ]
    return [tile for tile in tiles if tile.width > 0 and tile.depth > 0]
