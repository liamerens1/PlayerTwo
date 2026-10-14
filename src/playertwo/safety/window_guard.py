"""Only allow input while the game window is focused."""

from collections.abc import Callable

from playertwo.win32 import WindowInfo, foreground_window

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
        window_provider: Callable[[], WindowInfo] = foreground_window,
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
        return self.matches(self._window_provider())

    def matches(self, window: WindowInfo) -> bool:
        """Whether `window` is the game. Also used to find the game window to capture."""
        if not (self._title or self._process):
            return False
        process = window.process.casefold()
        if process in TERMINAL_PROCESSES:
            return False
        if self._process and process != self._process:
            return False
        return not self._title or self._title in window.title.casefold()
