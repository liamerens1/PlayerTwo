import itertools
import threading
import time

import numpy as np
import pytest

from playertwo.actions import Decision, GameProfile
from playertwo.brain import BrainUnavailableError, GameModel, InferenceStats
from playertwo.capture import ChangeDetector, FrameSource
from playertwo.config import LoopSettings
from playertwo.hands import ActionExecutor
from playertwo.orchestrator import GameLoop
from playertwo.types import Frame


class RecordingDriver:
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


class OpenGate:
    def __init__(self, open_: bool = True) -> None:
        self.open = open_

    def allows_input(self) -> bool:
        return self.open


class ChangingSource:
    """A new, different frame on every grab (a moving scene)."""

    def __init__(self) -> None:
        self.grabs = 0

    def grab(self) -> Frame | None:
        self.grabs += 1
        return np.full((8, 8, 3), self.grabs % 256, dtype=np.uint8)

    def close(self) -> None:
        pass


class StaticSource:
    """One frame, then nothing new (dxcam returns None while the screen is unchanged)."""

    def __init__(self) -> None:
        self._sent = False

    def grab(self) -> Frame | None:
        if self._sent:
            return None
        self._sent = True
        return np.zeros((8, 8, 3), dtype=np.uint8)

    def close(self) -> None:
        pass


class ScriptedModel(GameModel):
    def __init__(
        self, action: str = "interact", delay: float = 0.0, error: Exception | None = None
    ) -> None:
        self.action = action
        self.delay = delay
        self.error = error
        self.calls = 0

    def decide(self, frame: Frame, profile: GameProfile) -> Decision:
        self.calls += 1
        if self.error is not None:
            raise self.error
        time.sleep(self.delay)
        self.last_stats = InferenceStats(total_seconds=self.delay)
        return Decision(action=self.action, reason="test")


def _loop(
    profile: GameProfile,
    *,
    source: FrameSource | None = None,
    model: GameModel | None = None,
    gate: OpenGate | None = None,
    max_age: float = 5.0,
    republish: float = 10.0,
) -> tuple[GameLoop, RecordingDriver, threading.Event]:
    driver = RecordingDriver()
    stop = threading.Event()
    executor = ActionExecutor(driver, profile, stop, gate or OpenGate())
    loop = GameLoop(
        source or ChangingSource(),
        ChangeDetector(threshold=0.0),
        model or ScriptedModel(),
        executor,
        profile,
        stop,
        LoopSettings(max_decision_age_seconds=max_age),
        fps=100,
        republish_seconds=republish,
    )
    return loop, driver, stop


def _run_for(loop: GameLoop, stop: threading.Event, seconds: float) -> float:
    timer = threading.Timer(seconds, stop.set)
    timer.start()
    start = time.monotonic()
    try:
        loop.run()
    finally:
        timer.cancel()
    return time.monotonic() - start


def test_frames_flow_to_decisions_to_input(profile: GameProfile) -> None:
    loop, driver, stop = _loop(profile)
    elapsed = _run_for(loop, stop, 0.3)
    assert elapsed < 2
    assert loop.stats.decisions > 0
    assert loop.stats.actions_performed > 0
    assert ("press", "e") in driver.calls


def test_stop_ends_a_hold_and_releases_the_key(profile: GameProfile) -> None:
    long_hold = profile.model_copy(update={"max_hold_seconds": 10.0})
    loop, driver, stop = _loop(long_hold, model=ScriptedModel("move_forward"))
    elapsed = _run_for(loop, stop, 0.3)
    assert elapsed < 2
    assert ("down", "w") in driver.calls
    assert driver.calls[-1] == ("up", "w")


def test_stale_decisions_are_dropped(profile: GameProfile) -> None:
    # The model takes longer than the max age, so every decision is already stale.
    loop, driver, stop = _loop(profile, model=ScriptedModel(delay=0.1), max_age=0.05)
    _run_for(loop, stop, 0.5)
    assert loop.stats.decisions > 0
    assert loop.stats.dropped_stale == loop.stats.decisions
    assert driver.calls == []


def test_closed_gate_drops_input_but_keeps_deciding(profile: GameProfile) -> None:
    loop, driver, stop = _loop(profile, gate=OpenGate(open_=False))
    _run_for(loop, stop, 0.3)
    assert loop.stats.decisions > 0
    assert loop.stats.dropped_by_gate > 0
    assert driver.calls == []


def test_static_screen_is_republished_so_the_loop_never_stalls(profile: GameProfile) -> None:
    model = ScriptedModel()
    loop, _, stop = _loop(profile, source=StaticSource(), model=model, republish=0.05)
    _run_for(loop, stop, 0.4)
    assert model.calls >= 3


def test_static_screen_without_republish_decides_once(profile: GameProfile) -> None:
    model = ScriptedModel()
    loop, _, stop = _loop(profile, source=StaticSource(), model=model, republish=60)
    _run_for(loop, stop, 0.3)
    assert model.calls == 1


def test_brain_unavailable_stops_the_loop_and_is_reraised(profile: GameProfile) -> None:
    model = ScriptedModel(error=BrainUnavailableError("ollama is not running"))
    loop, _, stop = _loop(profile, model=model)
    with pytest.raises(BrainUnavailableError, match="not running"):
        _run_for(loop, stop, 5)
    assert stop.is_set()


def test_unexpected_error_in_a_thread_stops_and_releases(profile: GameProfile) -> None:
    long_hold = profile.model_copy(update={"max_hold_seconds": 10.0})

    class ExplodingSource(ChangingSource):
        def grab(self) -> Frame | None:
            if self.grabs > 20:
                raise RuntimeError("capture device lost")
            return super().grab()

    loop, driver, stop = _loop(
        long_hold, source=ExplodingSource(), model=ScriptedModel("move_forward")
    )
    start = time.monotonic()
    with pytest.raises(RuntimeError, match="capture device lost"):
        _run_for(loop, stop, 5)
    assert time.monotonic() - start < 3
    if ("down", "w") in driver.calls:
        assert driver.calls[-1] == ("up", "w")


def test_brain_always_sees_the_newest_frame(profile: GameProfile) -> None:
    seen: list[int] = []

    class SlowRecordingModel(ScriptedModel):
        def decide(self, frame: Frame, profile: GameProfile) -> Decision:
            seen.append(int(frame[0, 0, 0]))
            return super().decide(frame, profile)

    loop, _, stop = _loop(profile, model=SlowRecordingModel(action="wait", delay=0.05))
    _run_for(loop, stop, 0.4)
    # Capture runs at 100 fps and the model at about 20 decisions/s: frames in between are
    # skipped, never queued, so consecutive decisions see frames several grabs apart.
    assert loop.stats.frames_skipped > 0
    assert any(b - a > 1 for a, b in itertools.pairwise(seen))
