"""A game profile: everything game-specific, loaded from profiles/*.yaml."""

from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator

from playertwo.actions.action_spec import ActionSpec, WaitAction

WAIT_ACTION = "wait"


class GameProfile(BaseModel):
    """Goal, allowed actions and limits for one game."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str
    description: str = ""
    game_type: str = "third-person video game"
    """How the model is told what it's playing: "You control a character in a <game_type>"."""
    goal: str
    max_hold_seconds: float = Field(default=1.5, gt=0)
    actions: dict[str, ActionSpec]

    @field_validator("actions")
    @classmethod
    def _must_include_wait(cls, actions: dict[str, ActionSpec]) -> dict[str, ActionSpec]:
        # Every invalid model reply falls back to "wait", so it has to exist and be a no-op.
        spec = actions.get(WAIT_ACTION)
        if not isinstance(spec, WaitAction):
            raise ValueError(f"profile must define a '{WAIT_ACTION}' action of type 'wait'")
        return actions

    @property
    def action_names(self) -> list[str]:
        return list(self.actions)

    @classmethod
    def load(cls, path: Path) -> "GameProfile":
        with path.open(encoding="utf-8") as f:
            data = yaml.safe_load(f)
        return cls.model_validate(data)
