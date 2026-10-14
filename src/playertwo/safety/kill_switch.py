"""Global hotkey that stops everything. Phase 1."""

import threading


class KillSwitch:
    """Registers a global hotkey (default F12) that sets the shared stop event."""

    def __init__(self, hotkey: str, stop: threading.Event) -> None:
        self._hotkey = hotkey
        self._stop = stop

    def arm(self) -> None:
        raise NotImplementedError("Phase 1: feat/capture-input/1")

    def disarm(self) -> None:
        raise NotImplementedError("Phase 1: feat/capture-input/1")
