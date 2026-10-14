"""Real input via pydirectinput (DirectInput scan codes)."""

import logging
from types import ModuleType

logger = logging.getLogger(__name__)


class DirectInputDriver:
    """InputDriver backed by pydirectinput. Windows only; imported lazily.

    Only `ActionExecutor` should call this. It does no safety checks of its own: the
    executor's gate and kill switch decide whether input is allowed.
    """

    def __init__(self) -> None:
        import pydirectinput

        # No built-in sleep after every call: holds are timed by the executor, and a pause
        # would delay key-ups after the kill switch.
        pydirectinput.PAUSE = 0
        # The corner fail-safe also blocks keyUp, so a cursor parked at (0, 0) could leave a
        # key held down. F12 and the window guard are the stop mechanisms instead.
        pydirectinput.FAILSAFE = False
        self._pdi: ModuleType = pydirectinput

    def key_down(self, key: str) -> None:
        self._pdi.keyDown(self._checked(key))

    def key_up(self, key: str) -> None:
        self._pdi.keyUp(self._checked(key))

    def press(self, key: str) -> None:
        self._pdi.press(self._checked(key))

    def move_mouse(self, dx: int, dy: int) -> None:
        # relative=True sends a raw relative move, which game cameras read; the default
        # converts to an absolute cursor position, which most 3D games ignore.
        self._pdi.moveRel(dx, dy, relative=True)

    def _checked(self, key: str) -> str:
        # pydirectinput silently ignores names it doesn't know; fail loudly instead so a
        # profile typo shows up as an error, not as a character that never moves.
        mapping: dict[str, int | None] = self._pdi.KEYBOARD_MAPPING
        if mapping.get(key) is None:
            raise ValueError(f"pydirectinput has no scan code for key {key!r}")
        return key
