"""Everything model-specific lives here and nowhere else."""

from playertwo.brain.game_model import BrainUnavailableError, GameModel, InferenceStats
from playertwo.brain.ollama_vision_model import OllamaVisionModel, encode_jpeg
from playertwo.brain.prompt import (
    FRAME_PROMPT,
    REASON_MAX_CHARS,
    build_system_prompt,
    decision_schema,
)

__all__ = [
    "FRAME_PROMPT",
    "REASON_MAX_CHARS",
    "BrainUnavailableError",
    "GameModel",
    "InferenceStats",
    "OllamaVisionModel",
    "build_system_prompt",
    "decision_schema",
    "encode_jpeg",
]
