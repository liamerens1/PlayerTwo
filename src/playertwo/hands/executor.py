"""Turns a Decision into input, safely."""

import logging
import threading
import time

from playertwo.actions import (
    Decision,
    GameProfile,
    HoldAction,
    MouseAction,
    PressAction,
    WaitAction,
)
from playertwo.hands.input_driver import InputDriver
from playertwo.hands.input_gate import InputGate

logger = logging.getLogger(__name__)

GATE_POLL_SECONDS = 0.05
"""How often a hold re-checks the gate, so alt-tabbing out releases the key promptly."""


class ActionExecutor:
    """Performs decisions through an InputDriver.

    Safe on its own: asks the gate before every action and throughout every hold,
    re-validates the action, clamps hold time to the profile limit, aborts holds early on
    shutdown, and tracks held keys so they can always be released.
    """

    def __init__(
        self,
        driver: InputDriver,
        profile: GameProfile,
        stop: threading.Event,
        gate: InputGate,
    ) -> None:
        self._driver = driver
        self._profile = profile
        self._stop = stop
        self._gate = gate
        self._held: set[str] = set()
        self._lock = threading.Lock()

    def execute(self, decision: Decision) -> bool:
        """Perform the decision. False if it was dropped (stopped, or the gate is closed);
        a `wait` counts as performed."""
        if self._stop.is_set():
            return False
        decision = decision.validated_against(self._profile)
        spec = self._profile.actions[decision.action]
        if isinstance(spec, WaitAction):
            return True
        if not self._gate.allows_input():
            logger.debug("dropped %s: input gate closed", decision.action)
            return False
        logger.debug("executing %s (%s)", decision.action, decision.reason)

        match spec:
            case HoldAction(key=key, seconds=seconds):
                self._hold(key, min(seconds, self._profile.max_hold_seconds))
            case PressAction(key=key):
                self._driver.press(key)
            case MouseAction(dx=dx, dy=dy):
                self._driver.move_mouse(dx, dy)
        return True

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
        try:
            self._driver.key_down(key)
            deadline = time.monotonic() + seconds
            while (remaining := deadline - time.monotonic()) > 0:
                # Event.wait returns early on shutdown, so a hold never outlives the kill switch.
                if self._stop.wait(timeout=min(remaining, GATE_POLL_SECONDS)):
                    break
                if not self._gate.allows_input():
                    logger.debug("released %s early: input gate closed", key)
                    break
        finally:
            with self._lock:
                self._held.discard(key)
            # Always release, even if release_all already did: the kill switch can fire
            # between adding the key to _held and key_down, and a duplicate key-up is harmless.
            self._driver.key_up(key)
