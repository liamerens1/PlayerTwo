"""GameModel backed by any Ollama vision model."""

import io
import logging
import time

import httpx
import ollama
from PIL import Image
from pydantic import ValidationError

from playertwo.actions import WAIT_ACTION, Decision, GameProfile
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

    A single bad reply or failed call becomes `wait`. `max_consecutive_failures` of them in
    a row raise BrainUnavailableError, so a model that has stopped working (Ollama out of
    VRAM because the game took it, a crashed runner, a broken model) stops the loop
    instead of waiting forever.
    """

    def __init__(
        self, settings: BrainSettings, transport: httpx.BaseTransport | None = None
    ) -> None:
        self._settings = settings
        # Two clients only because the ollama client sets its timeout per client: a cold
        # load of a 4B/7B model can take far longer than one decision may.
        self._client = ollama.Client(
            host=settings.host, timeout=settings.timeout_seconds, transport=transport
        )
        self._loader = ollama.Client(
            host=settings.host, timeout=settings.warm_up_timeout_seconds, transport=transport
        )
        self._consecutive_failures = 0

    def warm_up(self) -> None:
        """Load the model into VRAM now; the first load can take tens of seconds."""
        start = time.monotonic()
        try:
            self._loader.generate(model=self._settings.model, keep_alive=self._settings.keep_alive)
        except ollama.ResponseError as exc:
            raise BrainUnavailableError(self._unavailable_message(exc)) from exc
        except ConnectionError as exc:
            raise BrainUnavailableError(str(exc)) from exc
        except httpx.TimeoutException as exc:
            raise BrainUnavailableError(
                f"{self._settings.model!r} did not load within "
                f"{self._settings.warm_up_timeout_seconds} s "
                "(raise brain.warm_up_timeout_seconds for large models)"
            ) from exc
        except httpx.TransportError as exc:
            raise BrainUnavailableError(
                f"Ollama dropped the connection while loading: {exc}"
            ) from exc
        logger.info("model %s ready in %.1f s", self._settings.model, time.monotonic() - start)

    def unload(self) -> None:
        """Free the model's VRAM now instead of after `keep_alive`. Best effort: never raises
        for Ollama being unreachable, since this runs during shutdown."""
        try:
            self._loader.generate(model=self._settings.model, keep_alive=0)
        except (ollama.ResponseError, ConnectionError, httpx.TransportError) as exc:
            logger.warning("could not unload %s: %s", self._settings.model, exc)
            return
        logger.info("model %s unloaded", self._settings.model)

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
        except httpx.TransportError as exc:
            # ReadError, RemoteProtocolError, ...: Ollama crashed or OOMed mid-reply.
            return self._fail(start, f"connection error {type(exc).__name__}: {exc}")

        self.last_stats = InferenceStats(
            total_seconds=time.monotonic() - start,
            load_seconds=(reply.load_duration or 0) / NANOSECONDS,
            prompt_seconds=(reply.prompt_eval_duration or 0) / NANOSECONDS,
            prompt_tokens=reply.prompt_eval_count or 0,
            reply_seconds=(reply.eval_duration or 0) / NANOSECONDS,
            reply_tokens=reply.eval_count or 0,
        )
        decision = self._parse(reply.response or "")
        if decision is None:
            return self._count_failure("unparseable reply")
        checked = decision.validated_against(profile)
        if checked is not decision:
            return self._count_failure(checked.reason or "unknown action")
        self._consecutive_failures = 0
        logger.debug(
            "decision %s in %.2f s (%s)",
            decision.action,
            self.last_stats.total_seconds,
            decision.reason,
        )
        return decision

    def _parse(self, text: str) -> Decision | None:
        try:
            return Decision.model_validate_json(text)
        except ValidationError:
            logger.warning("unparseable model reply, waiting instead: %.200r", text)
            return None

    def _fail(self, start: float, reason: str) -> Decision:
        self.last_stats = InferenceStats(total_seconds=time.monotonic() - start)
        logger.warning("model call failed, waiting instead: %s", reason)
        return self._count_failure(reason)

    def _count_failure(self, reason: str) -> Decision:
        self._consecutive_failures += 1
        limit = self._settings.max_consecutive_failures
        if self._consecutive_failures >= limit:
            raise BrainUnavailableError(
                f"{self._consecutive_failures} decisions in a row failed (last: {reason}). "
                "Is Ollama out of VRAM, or is the model broken?"
            )
        return Decision(action=WAIT_ACTION, reason=reason)

    def _unavailable_message(self, exc: ollama.ResponseError) -> str:
        if exc.status_code == httpx.codes.NOT_FOUND:
            return (
                f"model {self._settings.model!r} is not installed in Ollama. "
                f"Run: ollama pull {self._settings.model}"
            )
        return f"Ollama refused to load {self._settings.model!r}: {exc.error}"
