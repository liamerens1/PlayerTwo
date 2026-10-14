"""Combines the kill switch and window guard into the gate hands asks before any input."""

import time
from collections.abc import Callable

from playertwo.safety.kill_switch import KillSwitch
from playertwo.safety.window_guard import WindowGuard


class SafetyGate:
    """Satisfies `hands.InputGate`: input only while the kill switch is armed and the
    game window has been focused for at least `settle_seconds`.

    The settle delay exists because a key-down sent while a window is still activating
    lands before it has keyboard focus and is lost. Only the hands thread calls this.
    """

    def __init__(
        self,
        kill_switch: KillSwitch,
        window_guard: WindowGuard,
        settle_seconds: float = 0.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._kill_switch = kill_switch
        self._window_guard = window_guard
        self._settle_seconds = settle_seconds
        self._clock = clock
        self._focused_since: float | None = None

    def allows_input(self) -> bool:
        if not (self._kill_switch.armed and self._window_guard.game_is_focused()):
            self._focused_since = None
            return False
        now = self._clock()
        if self._focused_since is None:
            self._focused_since = now
        return now - self._focused_since >= self._settle_seconds
