"""Combines the kill switch and window guard into the gate hands asks before any input."""

from playertwo.safety.kill_switch import KillSwitch
from playertwo.safety.window_guard import WindowGuard


class SafetyGate:
    """Satisfies `hands.InputGate`: input only while the kill switch is armed and the
    game window has focus."""

    def __init__(self, kill_switch: KillSwitch, window_guard: WindowGuard) -> None:
        self._kill_switch = kill_switch
        self._window_guard = window_guard

    def allows_input(self) -> bool:
        return self._kill_switch.armed and self._window_guard.game_is_focused()
