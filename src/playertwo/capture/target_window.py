"""Finds the game window and reports where its client area is on screen."""

import threading
import time
from collections.abc import Callable

from playertwo.types import Rect
from playertwo.win32 import WindowInfo, client_rect, find_window, window_exists

REFIND_SECONDS = 0.5
"""How often to search all windows again while the game window can't be found."""


class TargetWindow:
    """Locates the window `matches` accepts (the same rule as the safety guard).

    The handle is cached; the search over every top-level window only runs again when
    the cached window is gone, and at most every REFIND_SECONDS. Moves and resizes are
    picked up on every call because the rectangle is read fresh each time.
    """

    def __init__(
        self,
        matches: Callable[[WindowInfo], bool],
        *,
        find: Callable[[Callable[[WindowInfo], bool]], int | None] = find_window,
        rect_of: Callable[[int], Rect | None] = client_rect,
        exists: Callable[[int], bool] = window_exists,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._matches = matches
        self._find = find
        self._rect_of = rect_of
        self._exists = exists
        self._clock = clock
        self._hwnd: int | None = None
        self._last_search: float | None = None
        self._lock = threading.Lock()  # capture thread and the app's game-closed check
        self.ever_found = False

    def handle(self) -> int | None:
        """The window's handle, or None if no matching window exists right now."""
        with self._lock:
            hwnd = self._hwnd
            if hwnd is not None and self._exists(hwnd):
                return hwnd
            self._hwnd = None
            now = self._clock()
            if self._last_search is not None and now - self._last_search < REFIND_SECONDS:
                return None
            self._last_search = now
            self._hwnd = self._find(self._matches)
            self.ever_found = self.ever_found or self._hwnd is not None
            return self._hwnd

    def rect(self) -> Rect | None:
        """The client area in screen pixels; None if the window is missing or minimised."""
        hwnd = self.handle()
        return None if hwnd is None else self._rect_of(hwnd)
