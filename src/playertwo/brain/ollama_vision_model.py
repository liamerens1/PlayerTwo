"""GameModel backed by any Ollama vision model."""

import io
import logging
import time

import httpx
import numpy as np
import ollama
from PIL import Image
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from playertwo.actions import WAIT_ACTION, Decision, GameProfile, History, Sighting, SteerTarget
from playertwo.brain.game_model import BrainUnavailableError, GameModel, InferenceStats
from playertwo.brain.prompt import (
    build_frame_prompt,
    build_locate_prompt,
    build_system_prompt,
    decision_schema,
    locate_schema,
)
from playertwo.config import BrainSettings
from playertwo.types import Frame

logger = logging.getLogger(__name__)

JPEG_QUALITY = 85
WARM_UP_FRAME_SHAPE = (360, 640)
"""Height, width of the blank frame used to warm up: the usual capture size, so the warm-up
processes as many image tokens as a real decision."""
NANOSECONDS = 1e9


def encode_jpeg(frame: Frame) -> bytes:
    """JPEG is much smaller than PNG for screenshots and quicker to send and decode."""
    buffer = io.BytesIO()
    Image.fromarray(frame).save(buffer, format="JPEG", quality=JPEG_QUALITY)
    return buffer.getvalue()


class _LocateReply(BaseModel):
    """What a locate reply must look like (also enforced by the schema sent to Ollama)."""

    model_config = ConfigDict(extra="ignore")

    visible: bool
    box: list[float] = Field(min_length=4, max_length=4)


class OllamaVisionModel(GameModel):
    """Sends a JPEG frame + the profile prompt to Ollama, parses JSON into a Decision.

    Works with any Ollama model that accepts images. Use non-thinking ("instruct") models:
    thinking models spend seconds reasoning before every answer.

    A single bad reply or failed call becomes `wait`. `max_consecutive_failures` of them in
    a row raise BrainUnavailableError, so a model that has stopped working (Ollama out of
    VRAM because the game took it, a crashed runner, a broken model) stops the loop
    instead of waiting forever.
    """

    can_locate = True

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

    def warm_up(self, profile: GameProfile | None = None) -> None:
        """Load the model into VRAM and, given the profile, make one throwaway decision on
        a blank frame, so the first real decision is as fast as the rest. Can take tens
        of seconds.

        A text-only load wasn't enough: right after loading, a freshly pulled 4B or 7B
        model took over 10 s on its first decisions (image encoder, system prompt and
        reply-format setup all cold), which timed out the start of a run (Phase 5).
        """
        start = time.monotonic()
        blank = np.full((*WARM_UP_FRAME_SHAPE, 3), 128, dtype=np.uint8)
        try:
            if profile is None:
                self._loader.generate(
                    model=self._settings.model, keep_alive=self._settings.keep_alive
                )
            else:
                self._generate(self._loader, blank, profile, None)
                if profile.target is not None:  # warm the locate request too
                    self._generate_locate(self._loader, blank, profile.target)
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

    def decide(
        self, frame: Frame, profile: GameProfile, history: History | None = None
    ) -> Decision:
        start = time.monotonic()
        try:
            reply = self._generate(self._client, frame, profile, history)
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

        self._record_stats(reply, start)
        assert self.last_stats is not None
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

    def locate(self, frame: Frame, target: SteerTarget) -> Sighting | None:
        start = time.monotonic()
        try:
            reply = self._generate_locate(self._client, frame, target)
        except ollama.ResponseError as exc:
            if exc.status_code == httpx.codes.NOT_FOUND:
                raise BrainUnavailableError(self._unavailable_message(exc)) from exc
            self._fail(start, f"ollama error {exc.status_code}: {exc.error}")
            return None
        except ConnectionError as exc:
            raise BrainUnavailableError(str(exc)) from exc
        except httpx.TimeoutException:
            self._fail(start, f"no reply within {self._settings.timeout_seconds} s")
            return None
        except httpx.TransportError as exc:
            self._fail(start, f"connection error {type(exc).__name__}: {exc}")
            return None

        self._record_stats(reply, start)
        sighting = self._parse_sighting(reply.response or "")
        if sighting is None:
            self._count_failure("unparseable locate reply")
            return None
        self._consecutive_failures = 0
        logger.debug("located %s: %s", target.description, sighting)
        return sighting

    def _generate_locate(
        self, client: ollama.Client, frame: Frame, target: SteerTarget
    ) -> ollama.GenerateResponse:
        """One locate request. Shared by `locate` and the warm-up."""
        return client.generate(
            model=self._settings.model,
            prompt=build_locate_prompt(target),
            images=[encode_jpeg(frame)],
            format=locate_schema(),
            options={
                "temperature": self._settings.temperature,
                "num_ctx": self._settings.context_tokens,
                "num_predict": self._settings.max_reply_tokens,
            },
            keep_alive=self._settings.keep_alive,
        )

    def _parse_sighting(self, text: str) -> Sighting | None:
        """A Sighting with the box as fractions of the frame, or None if the reply is
        unusable (bad JSON, or "visible" with a box of no width)."""
        try:
            reply = _LocateReply.model_validate_json(text)
        except ValidationError:
            logger.warning("unparseable locate reply, waiting instead: %.200r", text)
            return None
        if not reply.visible:
            return Sighting(visible=False)
        scale = self._settings.box_scale
        x1, y1, x2, y2 = (min(1.0, max(0.0, v / scale)) for v in reply.box)
        left, right = sorted((x1, x2))
        top, bottom = sorted((y1, y2))
        if right <= left:
            logger.warning("locate reply has an empty box, waiting instead: %.200r", text)
            return None
        return Sighting(visible=True, x=(left + right) / 2, box=(left, top, right, bottom))

    def _record_stats(self, reply: ollama.GenerateResponse, start: float) -> None:
        self.last_stats = InferenceStats(
            total_seconds=time.monotonic() - start,
            load_seconds=(reply.load_duration or 0) / NANOSECONDS,
            prompt_seconds=(reply.prompt_eval_duration or 0) / NANOSECONDS,
            prompt_tokens=reply.prompt_eval_count or 0,
            reply_seconds=(reply.eval_duration or 0) / NANOSECONDS,
            reply_tokens=reply.eval_count or 0,
        )

    def _generate(
        self,
        client: ollama.Client,
        frame: Frame,
        profile: GameProfile,
        history: History | None,
    ) -> ollama.GenerateResponse:
        """One decision request. Shared by `decide` and the warm-up, so the warm-up does
        exactly the work a real decision does."""
        return client.generate(
            model=self._settings.model,
            system=build_system_prompt(profile),
            prompt=build_frame_prompt(history),
            images=[encode_jpeg(frame)],
            format=decision_schema(profile),
            options={
                "temperature": self._settings.temperature,
                "num_ctx": self._settings.context_tokens,
                "num_predict": self._settings.max_reply_tokens,
            },
            keep_alive=self._settings.keep_alive,
        )

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
                f"{self._consecutive_failures} model calls in a row failed (last: {reason}). "
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
