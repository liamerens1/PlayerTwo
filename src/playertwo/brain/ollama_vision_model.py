"""GameModel backed by any Ollama vision model. Phase 2."""

from playertwo.actions import Decision, GameProfile
from playertwo.brain.game_model import GameModel
from playertwo.config import BrainSettings
from playertwo.types import Frame


class OllamaVisionModel(GameModel):
    """Sends a JPEG frame + the profile prompt to Ollama, parses JSON into a Decision."""

    def __init__(self, settings: BrainSettings) -> None:
        self._settings = settings

    def decide(self, frame: Frame, profile: GameProfile) -> Decision:
        raise NotImplementedError("Phase 2: feat/brain/2")
