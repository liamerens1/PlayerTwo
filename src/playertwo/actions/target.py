"""Look, then steer: what to look for (from the profile) and what the model saw."""

from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class SteerTarget(BaseModel):
    """A profile's `target:` section. The model only locates the target; steering code
    turns that into these actions. Everything here is game-specific, so it lives in the
    profile."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    description: str
    """What to look for, as the model is asked about it: "the yellow cube"."""
    forward: str
    """Action that moves towards the target once it's centred."""
    turn_left: str
    turn_right: str
    centre_width: float = Field(default=0.34, gt=0, lt=1)
    """Width of the "centred" band, as a fraction of the screen. Make it wider than one
    turn moves the view, or steering will swing from side to side past the target."""
    search: Literal["left", "right"] = "left"
    """Which way to turn while the target has never been seen."""
    nudge_left: str | None = None
    nudge_right: str | None = None
    """Optional small turns for fine aiming. A big turn near the target can swing it right
    across the screen and back (seen on the testbed); nudges settle it."""
    nudge_zone: float = Field(default=0.3, gt=0, le=0.5)
    """With nudges: a target within this distance of the screen centre (as a fraction of
    the width) gets a nudge rather than a full turn."""
    sidestep_left: str | None = None
    sidestep_right: str | None = None
    """Optional sideways moves that keep facing forward (strafe). When walking at the
    target stops changing the screen (blocked), steering detours sideways with these
    instead of handing over to the model, so the target stays in view."""
    detour_steps: int = Field(default=3, ge=1, le=20)
    """Sidesteps per detour."""


@dataclass(frozen=True)
class Sighting:
    """Where the model saw the target. Coordinates are fractions of the frame (0-1)."""

    visible: bool
    x: float | None = None
    """Horizontal centre of the target; None when not visible."""
    box: tuple[float, float, float, float] | None = None
    """(left, top, right, bottom), when the model gave one."""
