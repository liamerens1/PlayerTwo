"""Runtime settings, loaded from config/config.yaml."""

from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator

LOOPBACK_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})


class _Section(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class BrainSettings(_Section):
    provider: Literal["ollama"] = "ollama"
    model: str = "qwen3-vl:2b-instruct"
    host: str = "http://localhost:11434"
    temperature: float = Field(default=0.2, ge=0, le=2)
    context_tokens: int = Field(default=4096, gt=0)
    max_reply_tokens: int = Field(default=64, ge=8, le=1024)
    timeout_seconds: float = Field(default=10, gt=0)
    keep_alive: str = "30m"

    @field_validator("model")
    @classmethod
    def _local_model(cls, model: str) -> str:
        # Ollama serves "<name>:<tag>-cloud" / "<name>:cloud" models from Ollama's servers.
        # Every frame would leave the machine, which defeats the point of PlayerTwo.
        model = model.strip()
        tag = model.rpartition(":")[2] if ":" in model else ""
        if not model or tag == "cloud" or tag.endswith("-cloud"):
            raise ValueError(f"{model!r} is not a local model; cloud models are not allowed")
        return model

    @field_validator("host")
    @classmethod
    def _loopback_host(cls, host: str) -> str:
        # Local and free: the only network call in the loop is Ollama on this machine.
        hostname = urlsplit(host).hostname
        if hostname not in LOOPBACK_HOSTS:
            raise ValueError(f"brain.host must be on this machine (localhost), got {host!r}")
        return host


class CaptureSettings(_Section):
    width: int = Field(default=640, ge=64, le=3840)
    fps: int = Field(default=30, ge=1, le=240)
    change_threshold: float = Field(default=8.0, ge=0, le=255)


class SafetySettings(_Section):
    kill_switch: str = "f12"
    target_window: str = ""

    @field_validator("kill_switch")
    @classmethod
    def _single_key(cls, key: str) -> str:
        # The kill switch hooks one key's press so it fires whatever else is held down;
        # combos like ctrl+f12 can't work that way.
        key = key.strip().lower()
        if not key or "+" in key or "," in key:
            raise ValueError("kill_switch must be a single key name, e.g. 'f12'")
        return key


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
