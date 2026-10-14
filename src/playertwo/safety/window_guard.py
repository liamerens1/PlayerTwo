"""Only allow input while the game window is focused."""

import ctypes
import functools
import ntpath
import sys
from collections.abc import Callable
from dataclasses import dataclass

PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
MAX_PATH_CHARS = 32_768

TERMINAL_PROCESSES = frozenset(
    {
        "windowsterminal.exe",
        "openconsole.exe",
        "conhost.exe",
        "cmd.exe",
        "powershell.exe",
        "pwsh.exe",
        "powershell_ise.exe",
        "wt.exe",
        "mintty.exe",
        "bash.exe",
        "wsl.exe",
    }
)
"""Never a valid target. A terminal's title contains the running command line, so
`python -m playertwo --target-window Notepad` made the terminal itself match "Notepad"
and receive input (found in the Phase 3 live run)."""


@dataclass(frozen=True)
class ForegroundWindow:
    title: str
    process: str
    """Executable file name of the window's owner, e.g. "notepad.exe". "" if unknown."""


@functools.cache
def _user32() -> ctypes.CDLL:
    # CDLL rather than WinDLL so this type-checks on every OS; on 64-bit Windows there is
    # only one calling convention, so the two are equivalent.
    user32 = ctypes.CDLL("user32", use_last_error=True)
    user32.GetForegroundWindow.restype = ctypes.c_void_p
    user32.GetWindowTextLengthW.argtypes = [ctypes.c_void_p]
    user32.GetWindowTextW.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_int]
    user32.GetWindowThreadProcessId.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_ulong)]
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


def _window_title(hwnd: int) -> str:
    user32 = _user32()
    length = int(user32.GetWindowTextLengthW(hwnd))
    buffer = ctypes.create_unicode_buffer(length + 1)
    user32.GetWindowTextW(hwnd, buffer, length + 1)
    return buffer.value


def _window_process(hwnd: int) -> str:
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


def foreground_window() -> ForegroundWindow:
    """Title and owning executable of the focused window (empty when there is none, or
    when not on Windows)."""
    if sys.platform != "win32":
        return ForegroundWindow("", "")
    hwnd = _user32().GetForegroundWindow()
    if not hwnd:
        return ForegroundWindow("", "")
    return ForegroundWindow(_window_title(hwnd), _window_process(hwnd))


def foreground_window_title() -> str:
    """Title of the window that currently has focus, or "" if none (or not on Windows)."""
    return foreground_window().title


class WindowGuard:
    """Decides whether the focused window is the game.

    `target_process` (executable name, e.g. "game.exe") is the robust check;
    `target_window` (case-insensitive title substring) is optional and can be combined
    with it. Every configured check must pass. With neither configured, nothing matches,
    so an unconfigured guard blocks all input. Terminal and shell windows never match,
    whatever their title says.
    """

    def __init__(
        self,
        target_window: str = "",
        target_process: str = "",
        window_provider: Callable[[], ForegroundWindow] = foreground_window,
    ) -> None:
        self._title = target_window.strip().casefold()
        self._process = target_process.strip().casefold()
        self._window_provider = window_provider

    def describe(self) -> str:
        """Human-readable target, or "" if no target is configured."""
        parts = []
        if self._process:
            parts.append(f"process {self._process}")
        if self._title:
            parts.append(f"window titled *{self._title}*")
        return " and ".join(parts)

    def game_is_focused(self) -> bool:
        if not (self._title or self._process):
            return False
        window = self._window_provider()
        process = window.process.casefold()
        if process in TERMINAL_PROCESSES:
            return False
        if self._process and process != self._process:
            return False
        return not self._title or self._title in window.title.casefold()
