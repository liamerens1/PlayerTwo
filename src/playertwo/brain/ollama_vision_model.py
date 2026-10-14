"""GameModel backed by any Ollama vision model."""

import io
import logging
import time

import httpx
import ollama
from PIL import Image
from pydantic import ValidationError

from playertwo.actions import Decision, GameProfile
from playertwo.brain.game_model import BrainUnavailableError, GameModel, InferenceStats
from playertwo.brain.prompt import FRAME_PROMPT, build_system_prompt, decision_schema
from playertwo.config import BrainSettings
from playertwo.types import Frame

logger = logging.getLogger(__name__)

JPEG_QUALITY = 85
NANOSECONDS = 1e9


def encode_jpeg(frame: Frame) -> bytes:
    """JPEG is much smaller than PNG for screenshots and quicker to send and decode."""
    buffer = io.BytesIO()
    Image.fromarray(frame).save(buffer, format="JPEG", quality=JPEG_QUALITY)
    return buffer.getvalue()


class OllamaVisionModel(GameModel):
    """Sends a JPEG frame + the profile prompt to Ollama, parses JSON into a Decision.

    Works with any Ollama model that accepts images. Use non-thinking ("instruct") models:
    thinking models spend seconds reasoning before every answer.
    """

    def __init__(self, settings: BrainSettings, client: ollama.Client | None = None) -> None:
        self._settings = settings
        self._client = client or ollama.Client(host=settings.host, timeout=settings.timeout_seconds)

    def warm_up(self) -> None:
        """Load the model into VRAM now; the first load can take tens of seconds."""
        start = time.monotonic()
        try:
            self._client.generate(model=self._settings.model, keep_alive=self._settings.keep_alive)
        except ollama.ResponseError as exc:
            raise BrainUnavailableError(self._unavailable_message(exc)) from exc
        except ConnectionError as exc:
            raise BrainUnavailableError(str(exc)) from exc
        logger.info("model %s ready in %.1f s", self._settings.model, time.monotonic() - start)

    def decide(self, frame: Frame, profile: GameProfile) -> Decision:
        start = time.monotonic()
        try:
            reply = self._client.generate(
                model=self._settings.model,
                system=build_system_prompt(profile),
                prompt=FRAME_PROMPT,
                images=[encode_jpeg(frame)],
                format=decision_schema(profile),
                options={
                    "temperature": self._settings.temperature,
                    "num_ctx": self._settings.context_tokens,
                    "num_predict": self._settings.max_reply_tokens,
                },
                keep_alive=self._settings.keep_alive,
            )
        except ollama.ResponseError as exc:
            if exc.status_code == httpx.codes.NOT_FOUND:
                raise BrainUnavailableError(self._unavailable_message(exc)) from exc
            return self._fail(start, f"ollama error {exc.status_code}: {exc.error}")
        except ConnectionError as exc:
            raise BrainUnavailableError(str(exc)) from exc
        except httpx.TimeoutException:
            return self._fail(start, f"no reply within {self._settings.timeout_seconds} s")

        self.last_stats = InferenceStats(
            total_seconds=time.monotonic() - start,
            load_seconds=(reply.load_duration or 0) / NANOSECONDS,
            prompt_seconds=(reply.prompt_eval_duration or 0) / NANOSECONDS,
            prompt_tokens=reply.prompt_eval_count or 0,
            reply_seconds=(reply.eval_duration or 0) / NANOSECONDS,
            reply_tokens=reply.eval_count or 0,
        )
        decision = self._parse(reply.response or "").validated_against(profile)
        logger.debug(
            "decision %s in %.2f s (%s)",
            decision.action,
            self.last_stats.total_seconds,
            decision.reason,
        )
        return decision

    def _parse(self, text: str) -> Decision:
        try:
            return Decision.model_validate_json(text)
        except ValidationError:
            logger.warning("unparseable model reply, waiting instead: %.200r", text)
            return Decision.wait(reason="unparseable reply")

    def _fail(self, start: float, reason: str) -> Decision:
        self.last_stats = InferenceStats(total_seconds=time.monotonic() - start)
        logger.warning("model call failed, waiting instead: %s", reason)
        return Decision.wait(reason=reason)

    def _unavailable_message(self, exc: ollama.ResponseError) -> str:
        if exc.status_code == httpx.codes.NOT_FOUND:
            return (
                f"model {self._settings.model!r} is not installed in Ollama. "
                f"Run: ollama pull {self._settings.model}"
            )
        return f"Ollama refused to load {self._settings.model!r}: {exc.error}"
