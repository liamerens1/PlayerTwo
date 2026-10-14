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


class FakeGate:
    def __init__(self, open_: bool = True) -> None:
        self.open = open_

    def allows_input(self) -> bool:
        return self.open


def _executor(
    profile: GameProfile, gate: FakeGate | None = None
) -> tuple[ActionExecutor, RecordingInputDriver, threading.Event]:
    driver = RecordingInputDriver()
    stop = threading.Event()
    return ActionExecutor(driver, profile, stop, gate or FakeGate()), driver, stop


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


def test_closed_gate_drops_every_action(profile: GameProfile) -> None:
    executor, driver, _ = _executor(profile, FakeGate(open_=False))
    for action in ("move_forward", "interact", "turn_left", "turn_right"):
        executor.execute(Decision(action=action))
    assert driver.calls == []


def test_gate_closing_mid_hold_releases_key_early(profile: GameProfile) -> None:
    gate = FakeGate()
    executor, driver, _ = _executor(profile, gate)

    def close_gate() -> None:
        gate.open = False

    threading.Timer(0.05, close_gate).start()
    start = time.monotonic()
    executor.execute(Decision(action="move_forward"))
    assert time.monotonic() - start < 0.5
    assert driver.calls == [("down", "w"), ("up", "w")]


def test_release_all_lifts_a_key_held_on_another_thread(profile: GameProfile) -> None:
    executor, driver, stop = _executor(profile)
    worker = threading.Thread(target=executor.execute, args=(Decision(action="move_forward"),))
    worker.start()
    time.sleep(0.05)
    stop.set()
    executor.release_all()
    worker.join(timeout=1)
    assert not worker.is_alive()
    assert ("up", "w") in driver.calls
    assert driver.calls[-1] == ("up", "w")


def test_kill_switch_racing_key_down_still_releases(profile: GameProfile) -> None:
    # The kill switch fires after the key is registered as held but before key_down lands.
    # release_all's key-up then happens *before* the key-down; the hold must still lift it.
    stop = threading.Event()

    class RacingDriver(RecordingInputDriver):
        def key_down(self, key: str) -> None:
            stop.set()
            executor.release_all()
            super().key_down(key)

    driver = RacingDriver()
    executor = ActionExecutor(driver, profile, stop, FakeGate())
    executor.execute(Decision(action="move_forward"))
    assert driver.calls[-1] == ("up", "w")
