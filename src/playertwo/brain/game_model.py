"""The swappable model boundary. Every model adapter implements this."""

from abc import ABC, abstractmethod
from dataclasses import dataclass

from playertwo.actions import Decision, GameProfile, History, Sighting, SteerTarget
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
    """Timing of the most recent `decide` or `locate` call, if the adapter measures it."""

    can_locate: bool = False
    """Whether `locate` works. Without it, a profile's `target` is ignored and the model
    picks the action itself."""

    @abstractmethod
    def decide(
        self, frame: Frame, profile: GameProfile, history: History | None = None
    ) -> Decision:
        """Return one decision valid for `profile`. `history` is the short-term memory
        (recent actions and whether they changed the screen), if it's enabled.

        Must never raise for a bad model reply: return Decision.wait() instead. May raise
        BrainUnavailableError when the model can't be reached or isn't installed.
        """

    def locate(self, frame: Frame, target: SteerTarget) -> Sighting | None:
        """Look, then steer: where is `target` in `frame`? None if the model couldn't
        answer (a bad reply or failed call), which is not the same as "not visible".
        May raise BrainUnavailableError like `decide`. Only called if `can_locate`."""
        raise NotImplementedError(f"{type(self).__name__} can't locate targets")

    def warm_up(self, profile: GameProfile | None = None) -> None:  # noqa: B027 - optional hook
        """Load the model ahead of the first decision, ideally doing one throwaway
        decision for `profile` so the first real one isn't slow. Default: nothing to do."""

    def unload(self) -> None:  # noqa: B027 - optional hook, deliberately a no-op
        """Free the model's resources at shutdown. Must not raise. Default: nothing."""
