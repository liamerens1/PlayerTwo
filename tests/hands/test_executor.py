import threading
import time

from playertwo.actions import Decision, GameProfile
from playertwo.hands import ActionExecutor


class RecordingInputDriver:
    def __init__(self) -> None:
        self.calls: list[tuple[str, ...]] = []

    def key_down(self, key: str) -> None:
        self.calls.append(("down", key))

    def key_up(self, key: str) -> None:
        self.calls.append(("up", key))

    def press(self, key: str) -> None:
        self.calls.append(("press", key))

    def move_mouse(self, dx: int, dy: int) -> None:
        self.calls.append(("mouse", str(dx), str(dy)))


def _executor(profile: GameProfile) -> tuple[ActionExecutor, RecordingInputDriver, threading.Event]:
    driver = RecordingInputDriver()
    stop = threading.Event()
    return ActionExecutor(driver, profile, stop), driver, stop


def test_hold_presses_and_releases(profile: GameProfile) -> None:
    executor, driver, _ = _executor(profile.model_copy(update={"max_hold_seconds": 0.01}))
    executor.execute(Decision(action="move_forward"))
    assert driver.calls == [("down", "w"), ("up", "w")]


def test_hold_is_clamped_to_profile_max(profile: GameProfile) -> None:
    executor, _, _ = _executor(profile.model_copy(update={"max_hold_seconds": 0.05}))
    start = time.monotonic()
    executor.execute(Decision(action="move_forward"))
    assert time.monotonic() - start < 0.5


def test_stop_ends_a_hold_early_and_releases_key(profile: GameProfile) -> None:
    executor, driver, stop = _executor(profile)
    threading.Timer(0.05, stop.set).start()
    start = time.monotonic()
    executor.execute(Decision(action="move_forward"))
    assert time.monotonic() - start < 0.5
    assert driver.calls[-1] == ("up", "w")


def test_nothing_happens_after_stop(profile: GameProfile) -> None:
    executor, driver, stop = _executor(profile)
    stop.set()
    executor.execute(Decision(action="interact"))
    assert driver.calls == []


def test_unknown_action_does_nothing(profile: GameProfile) -> None:
    executor, driver, _ = _executor(profile)
    executor.execute(Decision(action="delete_save"))
    assert driver.calls == []


def test_press_and_mouse(profile: GameProfile) -> None:
    executor, driver, _ = _executor(profile)
    executor.execute(Decision(action="interact"))
    executor.execute(Decision(action="turn_left"))
    assert driver.calls == [("press", "e"), ("mouse", "-150", "0")]
