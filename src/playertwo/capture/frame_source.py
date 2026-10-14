"""The capture interface. Anything that can produce frames."""

from typing import Protocol

from playertwo.types import Frame


class FrameSource(Protocol):
    def grab(self) -> Frame | None:
        """Return the newest frame, or None if nothing new is available."""
        ...

    def close(self) -> None: ...
