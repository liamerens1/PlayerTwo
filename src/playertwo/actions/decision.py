"""What the brain hands to the hands: one chosen action."""

from pydantic import BaseModel, ConfigDict

from playertwo.actions.game_profile import WAIT_ACTION, GameProfile


class Decision(BaseModel):
    """One decision from the model. `action` is a name from the active profile."""

    model_config = ConfigDict(frozen=True, extra="ignore")

    action: str
    reason: str | None = None

    @classmethod
    def wait(cls, reason: str | None = None) -> "Decision":
        return cls(action=WAIT_ACTION, reason=reason)

    def validated_against(self, profile: GameProfile) -> "Decision":
        """Return self if the action exists in the profile, otherwise a wait."""
        if self.action in profile.actions:
            return self
        return Decision.wait(reason=f"unknown action {self.action!r}")
