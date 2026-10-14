import threading

from playertwo.safety import KillSwitch, SafetyGate, WindowGuard
from playertwo.win32 import WindowInfo
from tests.safety.test_kill_switch import FakeKeyHookBackend


class Clock:
    def __init__(self) -> None:
        self.now = 100.0

    def __call__(self) -> float:
        return self.now


def _gate(settle: float) -> tuple[SafetyGate, KillSwitch, list[str], Clock]:
    switch = KillSwitch("f12", threading.Event(), lambda: None, backend=FakeKeyHookBackend())
    title = ["Untitled - Notepad"]
    guard = WindowGuard("Notepad", window_provider=lambda: WindowInfo(title[0], "notepad.exe"))
    clock = Clock()
    return SafetyGate(switch, guard, settle_seconds=settle, clock=clock), switch, title, clock


def test_settle_delay_holds_input_until_focus_has_lasted() -> None:
    gate, switch, _, clock = _gate(settle=0.5)
    switch.arm()
    assert not gate.allows_input()  # just focused: still activating
    clock.now += 0.4
    assert not gate.allows_input()
    clock.now += 0.1
    assert gate.allows_input()


def test_losing_focus_restarts_the_settle_delay() -> None:
    gate, switch, title, clock = _gate(settle=0.5)
    switch.arm()
    gate.allows_input()
    clock.now += 1.0
    assert gate.allows_input()

    title[0] = "Command Prompt"
    assert not gate.allows_input()
    title[0] = "Untitled - Notepad"
    assert not gate.allows_input()
    clock.now += 0.5
    assert gate.allows_input()


def test_zero_settle_opens_immediately_but_still_needs_kill_switch() -> None:
    gate, switch, _, _ = _gate(settle=0.0)
    assert not gate.allows_input()
    switch.arm()
    assert gate.allows_input()
