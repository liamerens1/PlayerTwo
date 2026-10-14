"""The swappable model boundary. Every model adapter implements this."""

from abc import ABC, abstractmethod

from playertwo.actions import Decision, GameProfile
from playertwo.types import Frame


class GameModel(ABC):
    """Takes a frame and the active profile, returns one validated decision."""

    @abstractmethod
    def decide(self, frame: Frame, profile: GameProfile) -> Decision:
        """Must never raise for a bad model reply: return Decision.wait() instead."""
