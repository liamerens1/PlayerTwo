"""The swappable model boundary. Every model adapter implements this."""

from abc import ABC, abstractmethod
from dataclasses import dataclass

from playertwo.actions import Decision, GameProfile
from playertwo.types import Frame


class BrainUnavailableError(RuntimeError):
    """The model can't be used at all (server down, model not installed).

    Raised instead of returning `wait` so the caller can stop with a clear message,
    rather than looping forever on decisions that will never come.
    """


@dataclass(frozen=True)
class InferenceStats:
    """Timing for one decision. Durations in seconds."""

    total_seconds: float
    load_seconds: float = 0.0
    prompt_seconds: float = 0.0
    prompt_tokens: int = 0
    reply_seconds: float = 0.0
    reply_tokens: int = 0


class GameModel(ABC):
    """Takes a frame and the active profile, returns one validated decision."""

    last_stats: InferenceStats | None = None
    """Timing of the most recent `decide` call, if the adapter measures it."""

    @abstractmethod
    def decide(self, frame: Frame, profile: GameProfile) -> Decision:
        """Return one decision valid for `profile`.

        Must never raise for a bad model reply: return Decision.wait() instead. May raise
        BrainUnavailableError when the model can't be reached or isn't installed.
        """

    def warm_up(self) -> None:  # noqa: B027 - optional hook, deliberately a no-op
        """Load the model ahead of the first decision. Default: nothing to do."""

    def unload(self) -> None:  # noqa: B027 - optional hook, deliberately a no-op
        """Free the model's resources at shutdown. Must not raise. Default: nothing."""
