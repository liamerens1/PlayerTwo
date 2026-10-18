"""Runtime settings, loaded from config/config.yaml."""

from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

LOOPBACK_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})


class _Section(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class BrainSettings(_Section):
    provider: Literal["ollama"] = "ollama"
    model: str = "qwen3-vl:2b-instruct"
    host: str = "http://127.0.0.1:11434"
    """127.0.0.1, not localhost: on Windows "localhost" tries IPv6 first, and Ollama listens
    on IPv4 only, so every new connection waited about 2 s before falling back (Phase 5)."""
    temperature: float = Field(default=0.2, ge=0, le=2)
    context_tokens: int = Field(default=4096, gt=0)
    max_reply_tokens: int = Field(default=64, ge=8, le=1024)
    timeout_seconds: float = Field(default=10, gt=0)
    warm_up_timeout_seconds: float = Field(default=120, gt=0)
    """Loading a 4B/7B model cold can take far longer than one decision may."""
    max_consecutive_failures: int = Field(default=5, ge=1, le=1000)
    """This many bad replies or failed calls in a row stop the loop (BrainUnavailableError)."""
    keep_alive: str = "30m"
    box_scale: float = Field(default=1000.0, gt=0)
    """Look, then steer: the model's bounding-box coordinates are divided by this to get
    fractions of the frame. Qwen3-VL reports boxes on a 0-1000 grid (measured in Phase 6).
    Qwen2.5-VL uses a size-dependent pixel space instead and isn't supported for steering."""

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
    republish_seconds: float = Field(default=2.0, gt=0)
    """Re-send the last frame after this long without a change, so a static scene still
    gets decisions instead of stalling the loop."""


class SafetySettings(_Section):
    kill_switch: str = "f12"
    target_process: str = ""
    """Executable of the game, e.g. "game.exe". The reliable way to target a game."""
    target_window: str = ""
    """Optional title substring, checked as well if set. Titles are easy to match by
    accident (a terminal's title contains the command line that started PlayerTwo)."""
    focus_settle_seconds: float = Field(default=0.5, ge=0, le=10)
    """Input starts only after the target window has been focused this long. A key-down
    sent while a window is still activating is lost (found in Phase 1)."""

    @field_validator("kill_switch")
    @classmethod
    def _single_key(cls, key: str) -> str:
        # The kill switch hooks one key's press so it fires whatever else is held down;
        # combos like ctrl+f12 can't work that way.
        key = key.strip().lower()
        if not key or "+" in key or "," in key:
            raise ValueError("kill_switch must be a single key name, e.g. 'f12'")
        return key


class LoopSettings(_Section):
    max_decision_age_seconds: float = Field(default=5.0, gt=0, le=30)
    """Hands drops a decision whose frame was captured longer ago than this. With
    act-then-look a decision's age is about the model's thinking time, so this must be
    above the slowest model's decision time (was 1.5 s, set for the 0.6 s 2B model; a
    7B model takes seconds)."""
    wait_for_result: bool = True
    """Act, then look: decide only once the previous action has finished and settled, on
    the screen as it is then. Off: decide on the newest frame while the previous action
    may still be running (faster, but each decision is one action behind)."""
    settle_seconds: float = Field(default=0.15, ge=0, le=2)
    """Wait this long after an action before looking at the screen again, so the game
    has drawn its effect."""
    steer: bool = True
    """Look, then steer, for profiles with a `target:`: the model only locates the target
    and steering code picks the action. Off (or no target): the model picks the action."""


class MemorySettings(_Section):
    """Tier 1 short-term memory: the model sees its last few actions and whether they
    changed the screen, plus a hint when it keeps repeating one that does nothing."""

    enabled: bool = True
    size: int = Field(default=8, ge=1, le=32)
    """How many recent actions go into each prompt."""
    stuck_repeats: int = Field(default=3, ge=2, le=32)
    """The same action this many times in a row with no screen change counts as stuck."""
    change_threshold: float = Field(default=3.0, ge=0, le=255)
    """Mean per-pixel difference (0-255) between the screen before and after an action
    above which the action "changed the screen"."""

    @model_validator(mode="after")
    def _stuck_fits(self) -> "MemorySettings":
        if self.stuck_repeats > self.size:
            raise ValueError("memory.stuck_repeats can't be larger than memory.size")
        return self


class LoggingSettings(_Section):
    level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"


class Settings(_Section):
    brain: BrainSettings = BrainSettings()
    capture: CaptureSettings = CaptureSettings()
    profile: Path = Path("profiles/simple-walker.yaml")
    safety: SafetySettings = SafetySettings()
    loop: LoopSettings = LoopSettings()
    memory: MemorySettings = MemorySettings()
    logging: LoggingSettings = LoggingSettings()

    @classmethod
    def load(cls, path: Path) -> "Settings":
        with path.open(encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        return cls.model_validate(data)
