import sys
import threading
from collections.abc import Callable
from types import ModuleType

import pytest

from playertwo.safety import KillSwitch, SafetyGate, WindowGuard


class FakeKeyHookBackend:
    def __init__(self) -> None:
        self.hooks: dict[int, tuple[str, Callable[[], None]]] = {}
        self._next = 0

    def on_press(self, key: str, callback: Callable[[], None]) -> object:
        self._next += 1
        self.hooks[self._next] = (key, callback)
        return self._next

    def remove(self, handle: object) -> None:
        assert isinstance(handle, int)
        del self.hooks[handle]

    def press(self, key: str) -> None:
        for name, callback in list(self.hooks.values()):
            if name == key:
                callback()


def _kill_switch() -> tuple[KillSwitch, FakeKeyHookBackend, threading.Event, list[str]]:
    backend = FakeKeyHookBackend()
    stop = threading.Event()
    released: list[str] = []
    switch = KillSwitch("f12", stop, release=lambda: released.append("all"), backend=backend)
    return switch, backend, stop, released


def test_not_armed_until_arm() -> None:
    switch, backend, _, _ = _kill_switch()
    assert not switch.armed
    assert backend.hooks == {}


def test_arm_hooks_configured_key_once() -> None:
    switch, backend, _, _ = _kill_switch()
    switch.arm()
    switch.arm()
    assert switch.armed
    assert [name for name, _ in backend.hooks.values()] == ["f12"]


def test_key_press_sets_stop_and_releases() -> None:
    switch, backend, stop, released = _kill_switch()
    switch.arm()
    backend.press("f12")
    assert stop.is_set()
    assert released == ["all"]


def test_stop_is_set_before_release() -> None:
    stop = threading.Event()
    seen: list[bool] = []
    switch = KillSwitch(
        "f12", stop, release=lambda: seen.append(stop.is_set()), backend=FakeKeyHookBackend()
    )
    switch.trigger()
    assert seen == [True]


def test_other_keys_do_nothing() -> None:
    switch, backend, stop, released = _kill_switch()
    switch.arm()
    backend.press("f11")
    assert not stop.is_set()
    assert released == []


def test_disarm_unhooks() -> None:
    switch, backend, _, _ = _kill_switch()
    switch.arm()
    switch.disarm()
    switch.disarm()
    assert not switch.armed
    assert backend.hooks == {}


class FakeKeyboardModule(ModuleType):
    """Stands in for the `keyboard` library; records which API the kill switch uses."""

    def __init__(self) -> None:
        super().__init__("keyboard")
        self.press_hooks: dict[str, Callable[[object], None]] = {}
        self.unhooked: list[object] = []

    def on_press_key(self, key: str, callback: Callable[[object], None]) -> object:
        self.press_hooks[key] = callback
        return key

    def unhook(self, handle: object) -> None:
        self.unhooked.append(handle)

    def add_hotkey(self, *_args: object) -> None:
        raise AssertionError("add_hotkey ignores F12 while another key is held down")


def test_real_backend_hooks_the_key_itself(monkeypatch: pytest.MonkeyPatch) -> None:
    # Regression: keyboard.add_hotkey("f12") only fires when F12 is the *only* key down,
    # so it missed F12 while the executor held W. on_press_key matches F12 on its own.
    fake = FakeKeyboardModule()
    monkeypatch.setitem(sys.modules, "keyboard", fake)
    stop = threading.Event()
    switch = KillSwitch("f12", stop, release=lambda: None)

    switch.arm()
    fake.press_hooks["f12"](object())  # the library passes a KeyboardEvent
    switch.disarm()

    assert stop.is_set()
    assert fake.unhooked == ["f12"]


def test_safety_gate_needs_armed_switch_and_focused_window() -> None:
    switch, _, _, _ = _kill_switch()
    focused = WindowGuard("Notepad", title_provider=lambda: "Untitled - Notepad")
    unfocused = WindowGuard("Notepad", title_provider=lambda: "Command Prompt")

    assert not SafetyGate(switch, focused).allows_input()
    switch.arm()
    assert SafetyGate(switch, focused).allows_input()
    assert not SafetyGate(switch, unfocused).allows_input()
