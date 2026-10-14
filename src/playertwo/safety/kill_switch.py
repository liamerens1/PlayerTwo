"""Global key that stops everything."""

import logging
import threading
from collections.abc import Callable
from typing import Protocol

logger = logging.getLogger(__name__)


class KeyHookBackend(Protocol):
    """The slice of the `keyboard` library the kill switch uses. Faked in tests."""

    def on_press(self, key: str, callback: Callable[[], None]) -> object: ...

    def remove(self, handle: object) -> None: ...


class _KeyboardBackend:
    """KeyHookBackend backed by the `keyboard` library. Windows only; imported lazily.

    Uses `on_press_key`, not `add_hotkey`: `add_hotkey` only fires when the set of *all*
    pressed keys equals the hotkey, so it misses F12 while PlayerTwo is holding W, which
    is exactly when the kill switch matters.
    """

    def __init__(self) -> None:
        import keyboard

        self._keyboard = keyboard

    def on_press(self, key: str, callback: Callable[[], None]) -> object:
        handle: object = self._keyboard.on_press_key(key, lambda _event: callback())
        return handle

    def remove(self, handle: object) -> None:
        self._keyboard.unhook(handle)


class KillSwitch:
    """Hooks a global key (default F12) that sets the shared stop event.

    Fires on that key's own key-down, regardless of what else is held. `release` is called
    after the event is set; pass `executor.release_all` so every held key comes back up.
    Nothing should send input unless `armed` is True.
    """

    def __init__(
        self,
        key: str,
        stop: threading.Event,
        release: Callable[[], None],
        backend: KeyHookBackend | None = None,
    ) -> None:
        self._key = key
        self._stop = stop
        self._release = release
        self._backend = backend
        self._handle: object | None = None

    @property
    def armed(self) -> bool:
        return self._handle is not None

    def arm(self) -> None:
        if self.armed:
            return
        if self._backend is None:
            self._backend = _KeyboardBackend()
        self._handle = self._backend.on_press(self._key, self.trigger)
        logger.info("kill switch armed on %s", self._key)

    def disarm(self) -> None:
        if self._handle is None or self._backend is None:
            return
        self._backend.remove(self._handle)
        self._handle = None
        logger.info("kill switch disarmed")

    def trigger(self) -> None:
        """Stop everything. Runs on the key hook's thread; also callable directly."""
        logger.warning("kill switch triggered: stopping and releasing all input")
        # Stop first so nothing new starts, then release whatever is still held.
        self._stop.set()
        self._release()
