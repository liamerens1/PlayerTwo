"""Kill switch and foreground-window guard."""

from playertwo.safety.kill_switch import KeyHookBackend, KillSwitch
from playertwo.safety.safety_gate import SafetyGate
from playertwo.safety.window_guard import TERMINAL_PROCESSES, WindowGuard

__all__ = [
    "TERMINAL_PROCESSES",
    "KeyHookBackend",
    "KillSwitch",
    "SafetyGate",
    "WindowGuard",
]
