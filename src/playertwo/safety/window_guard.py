"""Only allow input while the game window is focused. Phase 1."""


class WindowGuard:
    """Checks the foreground window title contains the configured substring."""

    def __init__(self, target_window: str) -> None:
        self._target = target_window

    def game_is_focused(self) -> bool:
        raise NotImplementedError("Phase 1: feat/capture-input/1")
