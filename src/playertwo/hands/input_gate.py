"""The permission check hands asks before sending any input."""

from typing import Protocol


class InputGate(Protocol):
    def allows_input(self) -> bool:
        """True only if input may be sent right now (kill switch armed, game focused)."""
        ...
