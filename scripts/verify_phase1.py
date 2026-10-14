"""Manual live check for Phase 1: capture, input, window guard, kill switch.

Run from the repo root:

    python scripts\\verify_phase1.py

1. Captures one frame and saves it as a PNG.
2. With this terminal focused, asks the executor to hold a key: it must send nothing.
   Then opens Notepad if it isn't already open.
3. Asks you to focus Notepad, holds the key, and asks you to click back here: the key
   must be released as soon as Notepad loses focus.
4. Asks you to focus Notepad, holds the key, and asks you to press the kill switch: the
   key must be released immediately.

Sends real input only while the target window (default "Notepad") is focused.

Notepad shows a single character per hold, not a stream: injected key-downs don't
auto-repeat like a physical key. The checks read the OS key state (GetAsyncKeyState)
rather than trusting what appears in Notepad.
"""

import argparse
import ctypes
import logging
import subprocess
import sys
import threading
import time
from collections.abc import Callable
from pathlib import Path

from PIL import Image

from playertwo.actions import Decision, GameProfile, HoldAction
from playertwo.capture import DxcamFrameSource
from playertwo.config import Settings
from playertwo.hands import ActionExecutor, DirectInputDriver
from playertwo.safety import KillSwitch, SafetyGate, WindowGuard, foreground_window_title

ROOT = Path(__file__).resolve().parents[1]
HOLD_ACTION = "hold_key"
FOCUS_TIMEOUT_SECONDS = 15.0
RELEASE_BUDGET_SECONDS = 0.5
FOCUS_SETTLE_SECONDS = 1.0
"""Pause after the target gains focus: a key-down sent while the window is still activating
lands before its text area has keyboard focus and is lost."""


class CountingDriver:
    """Passes calls through to the real driver and records them."""

    def __init__(self, inner: DirectInputDriver) -> None:
        self._inner = inner
        self.calls: list[str] = []

    def key_down(self, key: str) -> None:
        self.calls.append(f"down {key}")
        self._inner.key_down(key)

    def key_up(self, key: str) -> None:
        self.calls.append(f"up {key}")
        self._inner.key_up(key)

    def press(self, key: str) -> None:
        self.calls.append(f"press {key}")
        self._inner.press(key)

    def move_mouse(self, dx: int, dy: int) -> None:
        self.calls.append(f"mouse {dx} {dy}")
        self._inner.move_mouse(dx, dy)


def _key_is_down(key: str) -> bool:
    """OS-level key state, so the check doesn't trust our own bookkeeping."""
    user32 = ctypes.CDLL("user32")
    vk = user32.VkKeyScanW(ord(key)) & 0xFF
    return bool(user32.GetAsyncKeyState(vk) & 0x8000)


def _window_exists(target: str) -> bool:
    """True if any visible top-level window's title contains `target` (case-insensitive)."""
    user32 = ctypes.CDLL("user32")
    user32.GetWindowTextLengthW.argtypes = [ctypes.c_void_p]
    user32.GetWindowTextW.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_int]
    user32.IsWindowVisible.argtypes = [ctypes.c_void_p]
    found = False

    def visit(hwnd: int, _: int) -> bool:
        nonlocal found
        if user32.IsWindowVisible(hwnd):
            length = int(user32.GetWindowTextLengthW(hwnd))
            buffer = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, buffer, length + 1)
            if target.casefold() in buffer.value.casefold():
                found = True
                return False  # stop enumerating
        return True

    callback = ctypes.CFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)(visit)
    user32.EnumWindows(callback, None)
    return found


def ensure_target_window_open(target: str) -> bool:
    """Open Notepad if it's the target and no window for it exists yet."""
    if _window_exists(target):
        return True
    if target.casefold() != "notepad":
        print(f"\n  No window titled *{target}* is open. Open it, then run this again.")
        return False
    print("\n  No Notepad window found: opening one.")
    subprocess.Popen(["notepad.exe"])
    if not _wait_until(lambda: _window_exists(target), 10.0):
        print("  Notepad didn't appear within 10 s.")
        return False
    return True


def _wait_until(condition: Callable[[], bool], timeout: float) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if condition():
            return True
        time.sleep(0.02)
    return condition()


def _hold_in_background(executor: ActionExecutor) -> threading.Thread:
    worker = threading.Thread(
        target=executor.execute, args=(Decision(action=HOLD_ACTION),), daemon=True
    )
    worker.start()
    return worker


def check_capture(settings: Settings, out: Path) -> bool:
    print("\n[1/4] Capture")
    source = DxcamFrameSource(settings.capture)
    try:
        frame = None
        deadline = time.monotonic() + 2.0
        while frame is None and time.monotonic() < deadline:
            frame = source.grab()
            if frame is None:
                time.sleep(0.05)
    finally:
        source.close()
    if frame is None:
        print("  FAIL: no frame within 2 s")
        return False
    Image.fromarray(frame).save(out)
    print(f"  frame {frame.shape[1]}x{frame.shape[0]} {frame.dtype}, saved to {out}")
    print("  PASS (open the PNG and check the colours look right, not blue-tinted)")
    return True


def check_dropped_when_unfocused(
    executor: ActionExecutor, driver: CountingDriver, guard: WindowGuard, key: str
) -> bool:
    print("\n[2/4] Input dropped while another window is focused")
    title = foreground_window_title()
    print(f"  focused window: {title!r}")
    if guard.game_is_focused():
        print(
            "  The target window is focused. Click on THIS terminal "
            f"(up to {FOCUS_TIMEOUT_SECONDS:.0f} s)..."
        )
        if not _wait_until(lambda: not guard.game_is_focused(), FOCUS_TIMEOUT_SECONDS):
            print("  FAIL: the target window stayed focused")
            return False
        print(f"  focused window: {foreground_window_title()!r}")
    executor.execute(Decision(action=HOLD_ACTION))
    sent = list(driver.calls)
    ok = sent == [] and not _key_is_down(key)
    print(f"  driver calls: {sent}")
    print("  PASS" if ok else "  FAIL: input reached the driver")
    return ok


def _focus_target(guard: WindowGuard, target: str) -> bool:
    print(f"  Click into the {target} window now (waiting up to {FOCUS_TIMEOUT_SECONDS:.0f} s)...")
    if not _wait_until(guard.game_is_focused, FOCUS_TIMEOUT_SECONDS):
        print(f"  FAIL: {target} was never focused")
        return False
    time.sleep(FOCUS_SETTLE_SECONDS)
    if not guard.game_is_focused():
        print(f"  FAIL: {target} lost focus again")
        return False
    return True


def check_release_on_focus_loss(
    executor: ActionExecutor, guard: WindowGuard, target: str, key: str
) -> bool:
    print("\n[3/4] Held key released when the target window loses focus")
    if not _focus_target(guard, target):
        return False
    start = time.monotonic()
    worker = _hold_in_background(executor)
    if not _wait_until(lambda: _key_is_down(key), 1.0):
        print(f"  FAIL: {key!r} never went down")
        worker.join(timeout=11)
        return False
    print(f"  {key!r} is held (expect one {key!r} in Notepad). Click back on THIS terminal now.")
    worker.join(timeout=11)
    elapsed = time.monotonic() - start
    released = not _key_is_down(key)
    ok = released and elapsed < 9.0 and not guard.game_is_focused()
    print(f"  hold ended after {elapsed:.2f} s, key released: {released}")
    print(f"  focused window now: {foreground_window_title()!r}")
    print("  PASS" if ok else "  FAIL: the hold ran its full length or the key is still down")
    return ok


def check_kill_switch(
    executor: ActionExecutor,
    guard: WindowGuard,
    stop: threading.Event,
    hotkey: str,
    target: str,
    key: str,
) -> bool:
    print(f"\n[4/4] {hotkey.upper()} stops a held key")
    if not _focus_target(guard, target):
        return False
    worker = _hold_in_background(executor)
    if not _wait_until(lambda: _key_is_down(key), 1.0):
        print(f"  FAIL: {key!r} never went down")
        worker.join(timeout=11)
        return False
    print(f"  {key!r} is held. Press {hotkey.upper()} ONCE now (keep {target} focused).")
    if not stop.wait(timeout=11):
        print(f"  FAIL: no {hotkey.upper()} press detected while {key!r} was held")
        worker.join(timeout=1)
        return False
    pressed_at = time.monotonic()
    released = _wait_until(lambda: not _key_is_down(key), RELEASE_BUDGET_SECONDS)
    worker.join(timeout=RELEASE_BUDGET_SECONDS)
    latency = time.monotonic() - pressed_at
    ok = released and not worker.is_alive()
    print(f"  stop event set; key released: {released}, hold thread finished in {latency:.2f} s")
    print("  PASS" if ok else "  FAIL: key still held after the kill switch")
    return ok


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--target", default="Notepad", help="substring of the target window")
    parser.add_argument("--process", default="notepad.exe", help="executable of the target")
    parser.add_argument("--out", type=Path, default=ROOT / "verify_phase1_frame.png")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="  %(levelname)s %(name)s: %(message)s")

    settings = Settings.load(ROOT / "config" / "config.yaml")
    profile = GameProfile.load(ROOT / "scripts" / "verify-notepad.yaml")
    spec = profile.actions[HOLD_ACTION]
    assert isinstance(spec, HoldAction)
    key = spec.key

    results = [check_capture(settings, args.out)]

    stop = threading.Event()
    guard = WindowGuard(target_window=args.target, target_process=args.process)
    driver = CountingDriver(DirectInputDriver())
    # The gate needs the kill switch and the kill switch releases the executor's keys; the
    # lambda looks `executor` up when the hotkey fires, by which point it exists.
    kill_switch = KillSwitch(
        settings.safety.kill_switch, stop, release=lambda: executor.release_all()
    )
    executor = ActionExecutor(driver, profile, stop, SafetyGate(kill_switch, guard))
    kill_switch.arm()
    try:
        results.append(check_dropped_when_unfocused(executor, driver, guard, key))
        if not ensure_target_window_open(args.target):
            return 1
        results.append(check_release_on_focus_loss(executor, guard, args.target, key))
        results.append(
            check_kill_switch(executor, guard, stop, settings.safety.kill_switch, args.target, key)
        )
    finally:
        stop.set()
        executor.release_all()
        kill_switch.disarm()

    passed = sum(results)
    print(f"\n{passed}/{len(results)} checks passed")
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(main())
