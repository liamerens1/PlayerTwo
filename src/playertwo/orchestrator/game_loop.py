"""Threaded capture -> brain -> hands loop. Phase 3."""

import threading

from playertwo.actions import GameProfile
from playertwo.brain import GameModel
from playertwo.capture import ChangeDetector, FrameSource
from playertwo.hands import ActionExecutor


class GameLoop:
    """Wires the components together on separate threads with single-slot hand-offs."""

    def __init__(
        self,
        source: FrameSource,
        detector: ChangeDetector,
        model: GameModel,
        executor: ActionExecutor,
        profile: GameProfile,
        stop: threading.Event,
    ) -> None:
        self._source = source
        self._detector = detector
        self._model = model
        self._executor = executor
        self._profile = profile
        self._stop = stop

    def run(self) -> None:
        raise NotImplementedError("Phase 3: feat/game-loop/3")
