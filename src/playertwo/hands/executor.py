"""Turns a Decision into input, safely."""

import logging
import threading

from playertwo.actions import (
    Decision,
    GameProfile,
    HoldAction,
    MouseAction,
    PressAction,
    WaitAction,
)
from playertwo.hands.input_driver import InputDriver

logger = logging.getLogger(__name__)


class ActionExecutor:
    """Performs decisions through an InputDriver.

    Safe on its own: re-validates the action, clamps hold time to the profile limit,
    aborts holds early on shutdown, and tracks held keys so they can always be released.
    """

    def __init__(self, driver: InputDriver, profile: GameProfile, stop: threading.Event) -> None:
        self._driver = driver
        self._profile = profile
        self._stop = stop
        self._held: set[str] = set()
        self._lock = threading.Lock()

    def execute(self, decision: Decision) -> None:
        if self._stop.is_set():
            return
        decision = decision.validated_against(self._profile)
        spec = self._profile.actions[decision.action]
        logger.debug("executing %s (%s)", decision.action, decision.reason)

        match spec:
            case HoldAction(key=key, seconds=seconds):
                self._hold(key, min(seconds, self._profile.max_hold_seconds))
            case PressAction(key=key):
                self._driver.press(key)
            case MouseAction(dx=dx, dy=dy):
                self._driver.move_mouse(dx, dy)
            case WaitAction():
                pass

    def release_all(self) -> None:
        """Release every key this executor holds. Called by the kill switch."""
        with self._lock:
            held = list(self._held)
            self._held.clear()
        for key in held:
            self._driver.key_up(key)

    def _hold(self, key: str, seconds: float) -> None:
        with self._lock:
            self._held.add(key)
        self._driver.key_down(key)
        try:
            # Event.wait returns early on shutdown, so a hold never outlives the kill switch.
            self._stop.wait(timeout=seconds)
        finally:
            with self._lock:
                still_held = key in self._held
                self._held.discard(key)
            if still_held:
                self._driver.key_up(key)
