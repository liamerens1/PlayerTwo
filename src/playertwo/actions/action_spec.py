"""The kinds of action a game profile can declare."""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field


class _ActionBase(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    description: str = ""


class HoldAction(_ActionBase):
    """Hold a key down for a number of seconds (e.g. walk forward)."""

    type: Literal["hold"]
    key: str
    seconds: float = Field(gt=0)


class PressAction(_ActionBase):
    """Tap a key once (e.g. interact)."""

    type: Literal["press"]
    key: str


class MouseAction(_ActionBase):
    """Move the mouse relatively (e.g. turn the camera)."""

    type: Literal["mouse"]
    dx: int = 0
    dy: int = 0


class WaitAction(_ActionBase):
    """Do nothing this turn."""

    type: Literal["wait"]


ActionSpec = Annotated[
    HoldAction | PressAction | MouseAction | WaitAction,
    Field(discriminator="type"),
]
"""Any action a profile can declare, discriminated on `type`."""
