"""Kill switch and foreground-window guard."""

from playertwo.safety.kill_switch import KeyHookBackend, KillSwitch
from playertwo.safety.safety_gate import SafetyGate
from playertwo.safety.window_guard import (
    TERMINAL_PROCESSES,
    ForegroundWindow,
    WindowGuard,
    foreground_window,
    foreground_window_title,
)

__all__ = [
    "TERMINAL_PROCESSES",
    "ForegroundWindow",
    "KeyHookBackend",
    "KillSwitch",
    "SafetyGate",
    "WindowGuard",
    "foreground_window",
    "foreground_window_title",
]
