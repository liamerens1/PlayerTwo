"""Threaded capture -> brain -> hands loop."""

import logging
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field

from playertwo.actions import Decision, GameProfile, Sighting, WaitAction
from playertwo.brain import GameModel
from playertwo.capture import ChangeDetector, FrameSource, frame_difference
from playertwo.config import LoopSettings, MemorySettings
from playertwo.hands import ActionExecutor
from playertwo.memory import ShortTermMemory
from playertwo.orchestrator.latest import Current, Latest
from playertwo.orchestrator.trace import Tracer
from playertwo.steering import Steerer
from playertwo.types import Frame

logger = logging.getLogger(__name__)

SLOT_TIMEOUT_SECONDS = 0.25
"""How long a thread waits on its input slot before re-checking the stop event."""
PAUSED_POLL_SECONDS = 0.1
"""How often capture checks whether the game has its focus back."""
SCREEN_POLL_SECONDS = 0.02
"""How often brain re-checks for a screen captured after the last action settled."""
JOIN_TIMEOUT_SECONDS = 5.0


@dataclass(frozen=True)
class TimedFrame:
    frame: Frame
    captured_at: float


@dataclass(frozen=True)
class TimedDecision:
    decision: Decision
    captured_at: float
    """When the frame this decision is about was captured."""


@dataclass
class LoopStats:
    """Counters, each written by exactly one thread; read them after `run` returns."""

    frames_published: int = 0
    decisions: int = 0
    decide_seconds: list[float] = field(default_factory=list)
    actions_performed: int = 0
    dropped_stale: int = 0
    dropped_by_gate: int = 0
    frames_skipped: int = 0
    decisions_skipped: int = 0
    paused_seconds: float = 0.0
    """Time capture and brain sat idle because the game wasn't focused."""
    stuck_hints: int = 0
    """Decisions made with the stuck detector's hint in the prompt."""
    steered: int = 0
    """Decisions made by look-then-steer (the rest were the model picking the action)."""
    target_seen: int = 0
    """Of those, how many times the model said the target was visible."""


def _always_focused() -> bool:
    return True


class GameLoop:
    """Wires the components together on separate threads with single-slot hand-offs.

    Capture publishes the newest frame when it changes (or every `republish_seconds` on a
    static screen); brain decides on the newest frame; hands performs the newest decision
    unless it's older than `max_decision_age_seconds`. Nothing ever queues.

    While `focused()` is False (the game isn't the foreground window) capture and brain
    idle, so the model doesn't spend GPU time the game needs on decisions that would be
    dropped anyway.

    With `wait_for_result` (the default) the brain waits for each action to finish and
    settle, then decides on the screen as it is now ("act, then look"). Otherwise it
    decides on the newest published frame while the previous action may still run.

    With memory enabled, hands compares the screen before and after each action it
    performs and records the result; the brain passes that history to the model.

    The caller warms the model up and arms the kill switch before `run`, and releases
    keys afterwards; `run` also releases them on the way out.
    """

    def __init__(
        self,
        source: FrameSource,
        detector: ChangeDetector,
        model: GameModel,
        executor: ActionExecutor,
        profile: GameProfile,
        stop: threading.Event,
        settings: LoopSettings,
        fps: int,
        republish_seconds: float,
        memory: MemorySettings | None = None,
        focused: Callable[[], bool] = _always_focused,
        tracer: Tracer | None = None,
    ) -> None:
        self._source = source
        self._detector = detector
        self._model = model
        self._executor = executor
        self._profile = profile
        self._stop = stop
        self._settings = settings
        self._frame_interval = 1.0 / fps
        self._republish_seconds = republish_seconds
        self._memory_settings = memory if memory is not None else MemorySettings(enabled=False)
        self._focused = focused
        self._tracer = tracer
        self._frames: Latest[TimedFrame] = Latest()
        self._decisions: Latest[TimedDecision] = Latest()
        self._screen: Current[TimedFrame] = Current()
        self._result_ready = threading.Event()
        self._result_ready.set()  # nothing to wait for before the first decision
        self._acted_at = 0.0
        """When the last action finished settling (written by hands, read by brain)."""
        self._failure: BaseException | None = None
        self._failure_lock = threading.Lock()
        target = profile.target
        self._target = target if settings.steer and model.can_locate else None
        self._steerer = Steerer(self._target) if self._target is not None else None
        self.memory: ShortTermMemory | None = (
            ShortTermMemory(self._memory_settings.size, self._memory_settings.stuck_repeats)
            if self._memory_settings.enabled
            else None
        )
        self.stats = LoopStats()

    def run(self) -> None:
        """Block until the stop event is set or a thread fails; re-raise that failure."""
        threads = [
            threading.Thread(target=self._guarded(self._capture_loop), name="capture"),
            threading.Thread(target=self._guarded(self._brain_loop), name="brain"),
            threading.Thread(target=self._guarded(self._hands_loop), name="hands"),
        ]
        for thread in threads:
            thread.start()
        try:
            while not self._stop.wait(timeout=SLOT_TIMEOUT_SECONDS):
                pass
        finally:
            self._stop.set()
            for thread in threads:
                thread.join(timeout=JOIN_TIMEOUT_SECONDS)
                if thread.is_alive():
                    logger.error(
                        "%s thread did not stop within %s s", thread.name, JOIN_TIMEOUT_SECONDS
                    )
            self._executor.release_all()
            self.stats.frames_skipped = self._frames.replaced
            self.stats.decisions_skipped = self._decisions.replaced
        if self._failure is not None:
            raise self._failure

    def _guarded(self, loop: Callable[[], None]) -> Callable[[], None]:
        def run() -> None:
            try:
                loop()
            except Exception as exc:  # top of a thread: log, record, stop everything
                logger.exception("%s thread failed; stopping", threading.current_thread().name)
                with self._failure_lock:
                    if self._failure is None:
                        self._failure = exc
            finally:
                self._stop.set()

        return run

    def _capture_loop(self) -> None:
        last: Frame | None = None
        last_published = 0.0
        paused = False
        while not self._stop.is_set():
            started = time.monotonic()
            if not self._focused():
                if not paused:
                    logger.info("game not focused: pausing capture and decisions")
                    paused = True
                    # Nothing captured before the pause may be decided on after it.
                    last = None
                    self._detector.reset()
                    self._frames.clear()
                    self._screen.clear()
                self._stop.wait(PAUSED_POLL_SECONDS)
                self.stats.paused_seconds += time.monotonic() - started
                continue
            if paused:
                logger.info("game focused again: resuming")
                paused = False
            frame = self._source.grab()
            if frame is not None:
                last = frame
            if last is not None:
                # dxcam returns None while nothing changed, so `last` is still what's on
                # screen now: stamp it with this grab's time.
                self._screen.set(TimedFrame(last, started))
            changed = frame is not None and self._detector.has_changed(frame)
            stale = last is not None and started - last_published >= self._republish_seconds
            if last is not None and (changed or stale):
                self._frames.put(TimedFrame(last, started))
                last_published = started
                self.stats.frames_published += 1
            self._stop.wait(max(0.0, self._frame_interval - (time.monotonic() - started)))

    def _next_frame(self) -> TimedFrame | None:
        """The frame to decide on next, or None to check the stop event and try again."""
        if not self._settings.wait_for_result:
            return self._frames.take(timeout=SLOT_TIMEOUT_SECONDS)
        # Act, then look: wait until the last action has finished and settled, then take
        # the screen as it is now. Deciding on a frame from before the last action ran
        # made the model repeat it (it kept turning left past the target).
        # Stopping cuts the last action short and wakes the brain: don't decide again.
        if not self._result_ready.wait(timeout=SLOT_TIMEOUT_SECONDS) or self._stop.is_set():
            return None
        timed = self._screen.get()
        if timed is None or timed.captured_at < self._acted_at:
            self._stop.wait(SCREEN_POLL_SECONDS)
            return None
        return timed

    def _brain_loop(self) -> None:
        while not self._stop.is_set():
            timed = self._next_frame()
            if timed is None or not self._focused():
                continue
            history = self.memory.snapshot() if self.memory is not None else None
            stuck = history is not None and history.stuck_action is not None
            if stuck:
                assert history is not None
                self.stats.stuck_hints += 1
                logger.debug("stuck hint: %s x%d", history.stuck_action, history.stuck_repeats)
            sighting: Sighting | None = None
            steerer, target = self._steerer, self._target
            # Look, then steer. When stuck (e.g. walking into a wall) steering detours
            # sideways if the profile can strafe; otherwise the model picks the action,
            # with the stuck hint, until something changes.
            steering = (
                steerer is not None and target is not None and (not stuck or steerer.can_detour)
            )
            asked_model = True
            if steering and steerer is not None and target is not None:
                asked_model = steerer.needs_look(stuck)
                if asked_model:
                    sighting = self._model.locate(timed.frame, target)
                    self.stats.target_seen += sighting is not None and sighting.visible
                decision = steerer.decide(sighting, stuck=stuck)
                self.stats.steered += 1
            else:
                decision = self._model.decide(timed.frame, self._profile, history)
            self.stats.decisions += 1
            model_seconds = None
            if self._model.last_stats is not None and asked_model:
                model_seconds = self._model.last_stats.total_seconds
                self.stats.decide_seconds.append(model_seconds)
            if self._tracer is not None:
                self._tracer.record(
                    timed.frame,
                    decision,
                    mode="steer" if steering else "pick",
                    sighting=sighting,
                    model_seconds=model_seconds,
                    stuck=stuck,
                )
            if self._settings.wait_for_result:
                self._result_ready.clear()  # before the hand-off, so hands' set() can't be lost
            self._decisions.put(TimedDecision(decision, timed.captured_at))

    def _hands_loop(self) -> None:
        max_age = self._settings.max_decision_age_seconds
        while not self._stop.is_set():
            timed = self._decisions.take(timeout=SLOT_TIMEOUT_SECONDS)
            if timed is None:
                continue
            age = time.monotonic() - timed.captured_at
            if age > max_age:
                logger.debug("dropped %s: %.2f s old", timed.decision.action, age)
                self.stats.dropped_stale += 1
            else:
                before = self._screen.get()
                if self._executor.execute(timed.decision):
                    self.stats.actions_performed += 1
                    self._after_action(timed.decision, before)
                else:
                    self.stats.dropped_by_gate += 1
            self._acted_at = time.monotonic()
            self._result_ready.set()

    def _after_action(self, decision: Decision, before: TimedFrame | None) -> None:
        """Let the game draw the action's effect, then record it in the memory."""
        decision = decision.validated_against(self._profile)
        if isinstance(self._profile.actions[decision.action], WaitAction):
            if self.memory is not None:
                self.memory.record(decision.action, decision.reason, None)
            return
        if not (self.memory is not None or self._settings.wait_for_result):
            return
        # Much shorter than a decision, and it's what makes the next look (and the
        # memory's before/after comparison) show this action's result.
        if self._stop.wait(self._settings.settle_seconds) or self.memory is None:
            return
        after = self._screen.get()
        changed: bool | None = None
        if before is not None and after is not None:
            difference = frame_difference(before.frame, after.frame)
            changed = difference > self._memory_settings.change_threshold
            logger.debug("%s changed the screen by %.1f", decision.action, difference)
        self.memory.record(decision.action, decision.reason, changed)
