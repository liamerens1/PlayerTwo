"""What the model is told about its own recent actions (Tier 1 short-term memory)."""

from dataclasses import dataclass


@dataclass(frozen=True)
class PastAction:
    """One action that was actually performed."""

    action: str
    reason: str
    screen_changed: bool | None
    """Whether the screen changed while it ran; None for actions where that means
    nothing (wait)."""


@dataclass(frozen=True)
class History:
    """The last few performed actions, oldest first, plus the stuck detector's verdict."""

    recent: tuple[PastAction, ...] = ()
    stuck_action: str | None = None
    """Set when the same action ran several times in a row without changing the screen."""
    stuck_repeats: int = 0
