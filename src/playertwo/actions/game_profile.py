"""A game profile: everything game-specific, loaded from profiles/*.yaml."""

from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from playertwo.actions.action_spec import ActionSpec, WaitAction
from playertwo.actions.target import SteerTarget

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
    target: SteerTarget | None = None
    """Optional. With a target, the model only locates it and steering code picks the
    action ("look, then steer"); without one, the model picks the action itself."""

    @field_validator("actions")
    @classmethod
    def _must_include_wait(cls, actions: dict[str, ActionSpec]) -> dict[str, ActionSpec]:
        # Every invalid model reply falls back to "wait", so it has to exist and be a no-op.
        spec = actions.get(WAIT_ACTION)
        if not isinstance(spec, WaitAction):
            raise ValueError(f"profile must define a '{WAIT_ACTION}' action of type 'wait'")
        if not spec.for_model:
            raise ValueError(f"'{WAIT_ACTION}' must be available to the model")
        return actions

    @model_validator(mode="after")
    def _target_uses_known_actions(self) -> "GameProfile":
        if self.target is None:
            return self
        steer = {
            "forward": self.target.forward,
            "turn_left": self.target.turn_left,
            "turn_right": self.target.turn_right,
        }
        if (self.target.nudge_left is None) != (self.target.nudge_right is None):
            raise ValueError("target.nudge_left and nudge_right go together: set both or neither")
        if self.target.nudge_left is not None and self.target.nudge_right is not None:
            steer["nudge_left"] = self.target.nudge_left
            steer["nudge_right"] = self.target.nudge_right
        if (self.target.sidestep_left is None) != (self.target.sidestep_right is None):
            raise ValueError(
                "target.sidestep_left and sidestep_right go together: set both or neither"
            )
        if self.target.sidestep_left is not None and self.target.sidestep_right is not None:
            steer["sidestep_left"] = self.target.sidestep_left
            steer["sidestep_right"] = self.target.sidestep_right
        for role, name in steer.items():
            if name not in self.actions:
                raise ValueError(f"target.{role} is {name!r}, which isn't one of the actions")
        if len(set(steer.values())) != len(steer):
            raise ValueError(
                "target actions (forward, turns, nudges, sidesteps) must all be different"
            )
        return self

    @property
    def action_names(self) -> list[str]:
        return list(self.actions)

    @property
    def model_action_names(self) -> list[str]:
        """The actions the model may pick (steering-only ones left out)."""
        return [name for name, spec in self.actions.items() if spec.for_model]

    @classmethod
    def load(cls, path: Path) -> "GameProfile":
        with path.open(encoding="utf-8") as f:
            data = yaml.safe_load(f)
        return cls.model_validate(data)
