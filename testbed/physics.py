"""Player movement, collisions and what counts as touching the target or falling.

Pure logic so episodes are deterministic and testable without a window. The Ursina front
end only draws the state this module computes.
"""

import math
from dataclasses import dataclass

from testbed.world import Layout, wrap_degrees

PLAYER_RADIUS = 0.5
MOVE_SPEED = 4.0
"""World units per second while a movement key is held."""
MAX_STEP_SECONDS = 0.1
"""Longer frames are split so a slow frame can't carry the player through a wall."""


@dataclass(frozen=True)
class PlayerState:
    x: float
    z: float
    heading: float


def start_state(layout: Layout) -> PlayerState:
    x, z = layout.start
    return PlayerState(x, z, layout.start_heading)


def blocked(layout: Layout, x: float, z: float) -> bool:
    """True if the player's body would overlap an obstacle at (x, z)."""
    return any(box.expanded(PLAYER_RADIUS).contains(x, z) for box in layout.obstacles)


def touching_target(layout: Layout, state: PlayerState) -> bool:
    return layout.target.expanded(PLAYER_RADIUS).contains(state.x, state.z)


def falling(layout: Layout, state: PlayerState) -> bool:
    """The player's centre is over the pit, or off the edge of an unfenced platform."""
    if layout.pit is not None and layout.pit.contains(state.x, state.z):
        return True
    return not layout.fenced and not layout.platform.contains(state.x, state.z)


def step(
    layout: Layout,
    state: PlayerState,
    forward: float,
    strafe: float,
    turn_degrees: float,
    dt: float,
) -> PlayerState:
    """Advance one frame. `forward` and `strafe` are -1..1 (W/S, D/A); `turn_degrees` is
    the turn this frame (mouse). Turning happens before moving."""
    heading = wrap_degrees(state.heading + turn_degrees)
    x, z = state.x, state.z
    length = math.hypot(forward, strafe)
    if length > 0 and dt > 0:
        scale = min(1.0, 1.0 / length)  # diagonal movement is no faster
        forward, strafe = forward * scale, strafe * scale
        rad = math.radians(heading)
        sin, cos = math.sin(rad), math.cos(rad)
        remaining = dt
        while remaining > 0:
            sub = min(remaining, MAX_STEP_SECONDS)
            remaining -= sub
            dx = (forward * sin + strafe * cos) * MOVE_SPEED * sub
            dz = (forward * cos - strafe * sin) * MOVE_SPEED * sub
            # One axis at a time, so the player slides along a wall instead of sticking.
            if not blocked(layout, x + dx, z):
                x += dx
            if not blocked(layout, x, z + dz):
                z += dz
            if layout.fenced:
                inner = layout.platform.expanded(-PLAYER_RADIUS)
                x = min(max(x, inner.min_x), inner.max_x)
                z = min(max(z, inner.min_z), inner.max_z)
    return PlayerState(x, z, heading)
