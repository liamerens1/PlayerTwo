import itertools
import threading
import time
from collections.abc import Callable

import numpy as np
import pytest

from playertwo.actions import Decision, GameProfile, History, PastAction
from playertwo.brain import BrainUnavailableError, GameModel, InferenceStats
from playertwo.capture import ChangeDetector, FrameSource
from playertwo.config import LoopSettings, MemorySettings
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
        self.histories: list[History | None] = []

    def decide(
        self, frame: Frame, profile: GameProfile, history: History | None = None
    ) -> Decision:
        self.calls += 1
        self.histories.append(history)
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
    memory: MemorySettings | None = None,
    focused: Callable[[], bool] = lambda: True,
    wait_for_result: bool = True,
    settle: float = 0.03,
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
        LoopSettings(
            max_decision_age_seconds=max_age, wait_for_result=wait_for_result, settle_seconds=settle
        ),
        fps=100,
        republish_seconds=republish,
        memory=memory,
        focused=focused,
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
    loop, _, stop = _loop(
        profile, source=StaticSource(), model=model, republish=0.05, wait_for_result=False
    )
    _run_for(loop, stop, 0.4)
    assert model.calls >= 3


def test_static_screen_without_republish_decides_once(profile: GameProfile) -> None:
    model = ScriptedModel()
    loop, _, stop = _loop(
        profile, source=StaticSource(), model=model, republish=60, wait_for_result=False
    )
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
        def decide(
            self, frame: Frame, profile: GameProfile, history: History | None = None
        ) -> Decision:
            seen.append(int(frame[0, 0, 0]))
            return super().decide(frame, profile, history)

    loop, _, stop = _loop(profile, model=SlowRecordingModel(action="wait", delay=0.05))
    _run_for(loop, stop, 0.4)
    # Capture runs at 100 fps and the model at about 20 decisions/s: frames in between are
    # skipped, never queued, so consecutive decisions see frames several grabs apart.
    assert loop.stats.frames_skipped > 0
    assert any(b - a > 1 for a, b in itertools.pairwise(seen))


class FrozenSource:
    """The same frame forever: whatever the character does, nothing on screen changes."""

    def grab(self) -> Frame | None:
        return np.zeros((8, 8, 3), dtype=np.uint8)

    def close(self) -> None:
        pass


QUICK_MEMORY = MemorySettings(change_threshold=0.5, stuck_repeats=2)
"""Capture runs at 100 fps in these tests, so the helper's 30 ms settle shows an effect."""


def test_unfocused_game_pauses_capture_and_decisions(profile: GameProfile) -> None:
    source = ChangingSource()
    model = ScriptedModel()
    loop, driver, stop = _loop(profile, source=source, model=model, focused=lambda: False)
    _run_for(loop, stop, 0.3)
    assert source.grabs == 0
    assert model.calls == 0
    assert driver.calls == []
    assert loop.stats.paused_seconds > 0.2


def test_decisions_resume_when_the_game_is_focused_again(profile: GameProfile) -> None:
    focus = threading.Event()
    model = ScriptedModel()
    loop, _, stop = _loop(profile, model=model, focused=focus.is_set)
    threading.Timer(0.2, focus.set).start()
    _run_for(loop, stop, 0.5)
    assert model.calls > 0
    assert 0.1 < loop.stats.paused_seconds < 0.4


def test_memory_off_passes_no_history(profile: GameProfile) -> None:
    model = ScriptedModel()
    loop, _, stop = _loop(profile, model=model)
    _run_for(loop, stop, 0.2)
    assert loop.memory is None
    assert model.histories and all(h is None for h in model.histories)


def test_memory_records_performed_actions_and_whether_the_screen_changed(
    profile: GameProfile,
) -> None:
    model = ScriptedModel("interact")
    loop, _, stop = _loop(profile, model=model, memory=QUICK_MEMORY)
    _run_for(loop, stop, 0.3)
    seen = [h for h in model.histories if h is not None and h.recent]
    assert seen, "the model never saw its own history"
    assert seen[-1].recent[-1] == PastAction("interact", "test", True)  # ChangingSource
    assert len(seen[-1].recent) <= QUICK_MEMORY.size


def test_wait_is_remembered_without_a_screen_verdict(profile: GameProfile) -> None:
    loop, _, stop = _loop(profile, model=ScriptedModel("wait"), memory=QUICK_MEMORY)
    _run_for(loop, stop, 0.2)
    assert loop.memory is not None
    recent = loop.memory.snapshot().recent
    assert recent and all(p == PastAction("wait", "test", None) for p in recent)


def test_dropped_actions_are_not_remembered(profile: GameProfile) -> None:
    loop, _, stop = _loop(profile, gate=OpenGate(open_=False), memory=QUICK_MEMORY)
    _run_for(loop, stop, 0.2)
    assert loop.memory is not None and loop.memory.snapshot().recent == ()


def test_repeating_an_action_that_changes_nothing_triggers_the_stuck_hint(
    profile: GameProfile,
) -> None:
    quick = profile.model_copy(update={"max_hold_seconds": 0.02})
    model = ScriptedModel("move_forward")
    loop, _, stop = _loop(
        quick, source=FrozenSource(), model=model, memory=QUICK_MEMORY, republish=0.02
    )
    _run_for(loop, stop, 0.5)
    stuck = [h for h in model.histories if h is not None and h.stuck_action is not None]
    assert stuck, "the stuck hint never reached the model"
    assert stuck[-1].stuck_action == "move_forward" and stuck[-1].stuck_repeats >= 2
    assert loop.stats.stuck_hints == len(stuck)


class TimedModel(ScriptedModel):
    """Records when each decision starts and which frame (by its first pixel) it saw."""

    def __init__(self, action: str) -> None:
        super().__init__(action)
        self.started: list[float] = []
        self.frames: list[int] = []

    def decide(
        self, frame: Frame, profile: GameProfile, history: History | None = None
    ) -> Decision:
        self.started.append(time.monotonic())
        self.frames.append(int(frame[0, 0, 0]))
        return super().decide(frame, profile, history)


def test_act_then_look_waits_for_each_action_to_finish(profile: GameProfile) -> None:
    # Regression: deciding while the last action was still running meant every decision
    # saw the screen from before it, so the model repeated turns past the target.
    hold = profile.model_copy(update={"max_hold_seconds": 0.1})
    model = TimedModel("move_forward")
    loop, _, stop = _loop(hold, model=model, settle=0.05)
    _run_for(loop, stop, 0.8)
    assert len(model.started) >= 3
    gaps = [b - a for a, b in itertools.pairwise(model.started)]
    assert min(gaps) >= 0.1 + 0.05 - 0.01  # the hold, then the settle
    assert loop.stats.decisions_skipped == 0  # nothing decided that hands then threw away


def test_act_then_look_decides_on_a_screen_captured_after_the_action(
    profile: GameProfile,
) -> None:
    source = ChangingSource()  # frame value = grab count, so later frames are larger
    hold = profile.model_copy(update={"max_hold_seconds": 0.05})
    model = TimedModel("move_forward")
    loop, _, stop = _loop(hold, source=source, model=model, settle=0.05)
    _run_for(loop, stop, 0.6)
    # Capture runs at 100 fps: a hold plus settle (0.1 s) is about 10 grabs apart.
    jumps = [b - a for a, b in itertools.pairwise(model.frames)]
    assert jumps and min(jumps) >= 8


def test_act_then_look_keeps_going_when_actions_are_dropped(profile: GameProfile) -> None:
    model = ScriptedModel("move_forward")
    loop, driver, stop = _loop(profile, model=model, gate=OpenGate(open_=False))
    _run_for(loop, stop, 0.3)
    assert model.calls >= 3  # a dropped action still releases the brain
    assert driver.calls == []
