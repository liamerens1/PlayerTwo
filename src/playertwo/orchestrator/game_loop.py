"""Threaded capture -> brain -> hands loop."""

import logging
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field

from playertwo.actions import Decision, GameProfile
from playertwo.brain import GameModel
from playertwo.capture import ChangeDetector, FrameSource
from playertwo.config import LoopSettings
from playertwo.hands import ActionExecutor
from playertwo.orchestrator.latest import Latest
from playertwo.types import Frame

logger = logging.getLogger(__name__)

SLOT_TIMEOUT_SECONDS = 0.25
"""How long a thread waits on its input slot before re-checking the stop event."""
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


class GameLoop:
    """Wires the components together on separate threads with single-slot hand-offs.

    Capture publishes the newest frame when it changes (or every `republish_seconds` on a
    static screen); brain decides on the newest frame; hands performs the newest decision
    unless it's older than `max_decision_age_seconds`. Nothing ever queues.

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
        self._frames: Latest[TimedFrame] = Latest()
        self._decisions: Latest[TimedDecision] = Latest()
        self._failure: BaseException | None = None
        self._failure_lock = threading.Lock()
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
        while not self._stop.is_set():
            started = time.monotonic()
            frame = self._source.grab()
            if frame is not None:
                last = frame
            changed = frame is not None and self._detector.has_changed(frame)
            stale = last is not None and started - last_published >= self._republish_seconds
            if last is not None and (changed or stale):
                self._frames.put(TimedFrame(last, started))
                last_published = started
                self.stats.frames_published += 1
            self._stop.wait(max(0.0, self._frame_interval - (time.monotonic() - started)))

    def _brain_loop(self) -> None:
        while not self._stop.is_set():
            timed = self._frames.take(timeout=SLOT_TIMEOUT_SECONDS)
            if timed is None:
                continue
            decision = self._model.decide(timed.frame, self._profile)
            self.stats.decisions += 1
            if self._model.last_stats is not None:
                self.stats.decide_seconds.append(self._model.last_stats.total_seconds)
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
                continue
            if self._executor.execute(timed.decision):
                self.stats.actions_performed += 1
            else:
                self.stats.dropped_by_gate += 1
