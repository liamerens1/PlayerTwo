"""Only allow input while the game window is focused."""

import ctypes
import functools
import sys
from collections.abc import Callable


@functools.cache
def _user32() -> ctypes.CDLL:
    # CDLL rather than WinDLL so this type-checks on every OS; on 64-bit Windows there is
    # only one calling convention, so the two are equivalent.
    user32 = ctypes.CDLL("user32", use_last_error=True)
    user32.GetForegroundWindow.restype = ctypes.c_void_p
    user32.GetWindowTextLengthW.argtypes = [ctypes.c_void_p]
    user32.GetWindowTextW.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_int]
    return user32


def foreground_window_title() -> str:
    """Title of the window that currently has focus, or "" if none (or not on Windows)."""
    if sys.platform != "win32":
        return ""
    user32 = _user32()
    hwnd = user32.GetForegroundWindow()
    if not hwnd:
        return ""
    length = int(user32.GetWindowTextLengthW(hwnd))
    buffer = ctypes.create_unicode_buffer(length + 1)
    user32.GetWindowTextW(hwnd, buffer, length + 1)
    return buffer.value


class WindowGuard:
    """Checks the foreground window title contains the configured substring.

    Case-insensitive. An empty target never matches: an unconfigured guard blocks all
    input rather than allowing it everywhere.
    """

    def __init__(
        self,
        target_window: str,
        title_provider: Callable[[], str] = foreground_window_title,
    ) -> None:
        self._target = target_window.strip().casefold()
        self._title_provider = title_provider

    def game_is_focused(self) -> bool:
        if not self._target:
            return False
        return self._target in self._title_provider().casefold()
