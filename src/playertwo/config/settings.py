"""Runtime settings, loaded from config/config.yaml."""

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field


class _Section(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class BrainSettings(_Section):
    provider: Literal["ollama"] = "ollama"
    model: str = "moondream"
    host: str = "http://localhost:11434"
    temperature: float = Field(default=0.2, ge=0, le=2)
    context_tokens: int = Field(default=4096, gt=0)
    timeout_seconds: float = Field(default=10, gt=0)


class CaptureSettings(_Section):
    width: int = Field(default=640, ge=64, le=3840)
    fps: int = Field(default=30, ge=1, le=240)
    change_threshold: float = Field(default=8.0, ge=0, le=255)


class SafetySettings(_Section):
    kill_switch: str = "f12"
    target_window: str = ""


class LoggingSettings(_Section):
    level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"


class Settings(_Section):
    brain: BrainSettings = BrainSettings()
    capture: CaptureSettings = CaptureSettings()
    profile: Path = Path("profiles/simple-walker.yaml")
    safety: SafetySettings = SafetySettings()
    logging: LoggingSettings = LoggingSettings()

    @classmethod
    def load(cls, path: Path) -> "Settings":
        with path.open(encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        return cls.model_validate(data)
