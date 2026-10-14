"""Small Win32 helpers for finding windows: title, owning executable, client area.

Shared by `safety` (is the game focused?) and `capture` (where is the game on screen?).
Every function returns an empty / None result off Windows, so callers stay testable.
"""

import ctypes
import functools
import ntpath
import sys
from collections.abc import Callable
from dataclasses import dataclass

from playertwo.types import Rect

PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
MAX_PATH_CHARS = 32_768
DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2 = -4


@dataclass(frozen=True)
class WindowInfo:
    title: str
    process: str
    """Executable file name of the window's owner, e.g. "notepad.exe". "" if unknown."""


class _Point(ctypes.Structure):
    _fields_ = (("x", ctypes.c_long), ("y", ctypes.c_long))


class _Rect(ctypes.Structure):
    _fields_ = (
        ("left", ctypes.c_long),
        ("top", ctypes.c_long),
        ("right", ctypes.c_long),
        ("bottom", ctypes.c_long),
    )


_EnumWindowsProc = ctypes.CFUNCTYPE(ctypes.c_int, ctypes.c_void_p, ctypes.c_void_p)


@functools.cache
def _user32() -> ctypes.CDLL:
    # CDLL rather than WinDLL so this type-checks on every OS; on 64-bit Windows there is
    # only one calling convention, so the two are equivalent.
    user32 = ctypes.CDLL("user32", use_last_error=True)
    user32.GetForegroundWindow.restype = ctypes.c_void_p
    user32.GetWindowTextLengthW.argtypes = [ctypes.c_void_p]
    user32.GetWindowTextW.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_int]
    user32.GetWindowThreadProcessId.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_ulong)]
    user32.EnumWindows.argtypes = [_EnumWindowsProc, ctypes.c_void_p]
    user32.IsWindow.argtypes = [ctypes.c_void_p]
    user32.IsWindowVisible.argtypes = [ctypes.c_void_p]
    user32.IsIconic.argtypes = [ctypes.c_void_p]
    user32.GetClientRect.argtypes = [ctypes.c_void_p, ctypes.POINTER(_Rect)]
    user32.ClientToScreen.argtypes = [ctypes.c_void_p, ctypes.POINTER(_Point)]
    user32.SetProcessDpiAwarenessContext.argtypes = [ctypes.c_void_p]
    return user32


@functools.cache
def _kernel32() -> ctypes.CDLL:
    kernel32 = ctypes.CDLL("kernel32", use_last_error=True)
    kernel32.OpenProcess.restype = ctypes.c_void_p
    kernel32.OpenProcess.argtypes = [ctypes.c_ulong, ctypes.c_int, ctypes.c_ulong]
    kernel32.QueryFullProcessImageNameW.argtypes = [
        ctypes.c_void_p,
        ctypes.c_ulong,
        ctypes.c_wchar_p,
        ctypes.POINTER(ctypes.c_ulong),
    ]
    kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
    return kernel32


@functools.cache
def make_dpi_aware() -> None:
    """Use real pixels for window coordinates. Without this, on a display scaled above
    100% Windows reports scaled-down rectangles that don't match what dxcam captures.
    dxcam asks for the same when it loads; calling it twice is harmless."""
    if sys.platform == "win32":
        _user32().SetProcessDpiAwarenessContext(DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2)


def window_title(hwnd: int) -> str:
    user32 = _user32()
    length = int(user32.GetWindowTextLengthW(hwnd))
    buffer = ctypes.create_unicode_buffer(length + 1)
    user32.GetWindowTextW(hwnd, buffer, length + 1)
    return buffer.value


def window_process(hwnd: int) -> str:
    pid = ctypes.c_ulong(0)
    _user32().GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    kernel32 = _kernel32()
    handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid.value)
    if not handle:
        return ""
    try:
        size = ctypes.c_ulong(MAX_PATH_CHARS)
        buffer = ctypes.create_unicode_buffer(MAX_PATH_CHARS)
        if not kernel32.QueryFullProcessImageNameW(handle, 0, buffer, ctypes.byref(size)):
            return ""
        return ntpath.basename(buffer.value)
    finally:
        kernel32.CloseHandle(handle)


def window_info(hwnd: int) -> WindowInfo:
    return WindowInfo(window_title(hwnd), window_process(hwnd))


def foreground_window() -> WindowInfo:
    """Title and owning executable of the focused window (empty when there is none, or
    when not on Windows)."""
    if sys.platform != "win32":
        return WindowInfo("", "")
    hwnd = _user32().GetForegroundWindow()
    if not hwnd:
        return WindowInfo("", "")
    return window_info(hwnd)


def find_window(matches: Callable[[WindowInfo], bool]) -> int | None:
    """Handle of the first visible top-level window `matches` accepts, or None."""
    if sys.platform != "win32":
        return None
    user32 = _user32()
    found: list[int] = []

    def visit(hwnd: int | None, _: int | None) -> int:
        if hwnd and user32.IsWindowVisible(hwnd) and matches(window_info(hwnd)):
            found.append(hwnd)
            return 0  # stop enumerating
        return 1

    user32.EnumWindows(_EnumWindowsProc(visit), None)
    return found[0] if found else None


def window_exists(hwnd: int) -> bool:
    return sys.platform == "win32" and bool(_user32().IsWindow(hwnd))


def client_rect(hwnd: int) -> Rect | None:
    """The window's client area (no title bar or borders) in screen pixels, or None if
    the window is gone or minimised."""
    if sys.platform != "win32":
        return None
    user32 = _user32()
    if not user32.IsWindow(hwnd) or user32.IsIconic(hwnd):
        return None
    make_dpi_aware()
    rect = _Rect()
    if not user32.GetClientRect(hwnd, ctypes.byref(rect)):
        return None
    origin = _Point(0, 0)
    if not user32.ClientToScreen(hwnd, ctypes.byref(origin)):
        return None
    return Rect(origin.x, origin.y, origin.x + rect.right, origin.y + rect.bottom)
