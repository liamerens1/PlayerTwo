"""A path planner and a simple controller that drives it.

Used to prove every generated level can be won (tests), to reject unwinnable level-4
layouts, and by `--autopilot` to demo the game without sending any real input.
"""

import math
from collections import deque
from dataclasses import dataclass

from testbed.physics import PLAYER_RADIUS, PlayerState, touching_target
from testbed.world import Layout, heading_towards, wrap_degrees

GRID = 0.5
"""Planner cell size in world units."""
CLEARANCE = 0.25
"""Extra room the planner keeps from walls, pits and edges beyond the player's radius."""
TURN_RATE = 240.0
"""Degrees per second the autopilot turns."""
AIM_TOLERANCE = 25.0
"""Walk only when facing within this many degrees of the next waypoint."""
WAYPOINT_REACHED = 0.35


def _free(layout: Layout, x: float, z: float) -> bool:
    margin = PLAYER_RADIUS + CLEARANCE
    if any(box.expanded(margin).contains(x, z) for box in layout.obstacles):
        return False
    if layout.pit is not None and layout.pit.expanded(margin).contains(x, z):
        return False
    edge = PLAYER_RADIUS if layout.fenced else margin
    return layout.platform.expanded(-edge).contains(x, z)


def plan_path(layout: Layout) -> list[tuple[float, float]] | None:
    """Waypoints from the start to the target on a grid, or None if it can't be reached."""
    sx, sz = layout.start
    origin_x, origin_z = layout.platform.min_x, layout.platform.min_z
    cols = math.ceil(layout.platform.width / GRID) + 1
    rows = math.ceil(layout.platform.depth / GRID) + 1

    def point(cell: tuple[int, int]) -> tuple[float, float]:
        return origin_x + cell[0] * GRID, origin_z + cell[1] * GRID

    start = (round((sx - origin_x) / GRID), round((sz - origin_z) / GRID))
    goal_area = layout.target.expanded(PLAYER_RADIUS - GRID / 2)
    came_from: dict[tuple[int, int], tuple[int, int] | None] = {start: None}
    queue = deque([start])
    while queue:
        cell = queue.popleft()
        x, z = point(cell)
        if goal_area.contains(x, z):
            path = []
            current: tuple[int, int] | None = cell
            while current is not None:
                path.append(point(current))
                current = came_from[current]
            path.reverse()
            return path
        for dc, dr in ((1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (1, -1), (-1, 1), (-1, -1)):
            nxt = (cell[0] + dc, cell[1] + dr)
            if nxt in came_from or not (0 <= nxt[0] < cols and 0 <= nxt[1] < rows):
                continue
            nx, nz = point(nxt)
            in_goal = goal_area.contains(nx, nz)
            if not in_goal and not _free(layout, nx, nz):
                continue
            # No cutting corners diagonally past an obstacle.
            if (
                dc
                and dr
                and not (_free(layout, x + dc * GRID, z) and _free(layout, x, z + dr * GRID))
            ):
                continue
            came_from[nxt] = cell
            queue.append(nxt)
    return None


@dataclass(frozen=True)
class Command:
    forward: float
    turn_degrees: float


class Autopilot:
    """Follows a planned path: turn towards the next waypoint, walk when facing it."""

    def __init__(self, layout: Layout) -> None:
        self._layout = layout
        self._path = plan_path(layout) or []
        self._next = 1 if len(self._path) > 1 else 0

    @property
    def has_path(self) -> bool:
        return bool(self._path)

    def command(self, state: PlayerState, dt: float) -> Command:
        if not self._path or touching_target(self._layout, state):
            return Command(0.0, 0.0)
        while self._next < len(self._path) - 1:
            wx, wz = self._path[self._next]
            if math.hypot(wx - state.x, wz - state.z) > WAYPOINT_REACHED:
                break
            self._next += 1
        wx, wz = self._path[self._next]
        if self._next == len(self._path) - 1:
            wx, wz = self._layout.target.center  # last stretch: aim at the cube itself
        error = wrap_degrees(heading_towards(state.x, state.z, wx, wz) - state.heading)
        max_turn = TURN_RATE * dt
        turn = max(-max_turn, min(max_turn, error))
        forward = 1.0 if abs(error - turn) < AIM_TOLERANCE else 0.0
        return Command(forward, turn)
