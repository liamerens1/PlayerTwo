import base64
import io
import json
import logging
from collections.abc import Callable
from typing import Any

import httpx
import numpy as np
import pytest
from PIL import Image

from playertwo.actions import GameProfile, History, PastAction
from playertwo.brain import (
    FRAME_PROMPT,
    BrainUnavailableError,
    OllamaVisionModel,
    build_frame_prompt,
    build_system_prompt,
    encode_jpeg,
)
from playertwo.config import BrainSettings
from playertwo.types import Frame

Handler = Callable[[httpx.Request], httpx.Response]


def _frame() -> Frame:
    return np.full((36, 64, 3), (200, 40, 40), dtype=np.uint8)


def _reply(text: str, **extra: Any) -> httpx.Response:
    body = {
        "model": "qwen3-vl:2b-instruct",
        "response": text,
        "done": True,
        "load_duration": 1_000_000,
        "prompt_eval_count": 1128,
        "prompt_eval_duration": 410_000_000,
        "eval_count": 22,
        "eval_duration": 100_000_000,
        **extra,
    }
    return httpx.Response(200, json=body)


class FakeOllama:
    """Records every request and answers with whatever `handler` returns."""

    def __init__(self, handler: Handler) -> None:
        self.requests: list[dict[str, Any]] = []
        self.read_timeouts: list[float] = []
        self._handler = handler

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(json.loads(request.content or b"{}"))
        self.read_timeouts.append(request.extensions["timeout"]["read"])
        return self._handler(request)


def _model(handler: Handler, **settings: Any) -> tuple[OllamaVisionModel, FakeOllama]:
    fake = FakeOllama(handler)
    return OllamaVisionModel(BrainSettings(**settings), transport=httpx.MockTransport(fake)), fake


def test_valid_reply_becomes_decision(profile: GameProfile) -> None:
    model, _ = _model(lambda _: _reply('{"action": "turn_left", "reason": "wall ahead"}'))
    decision = model.decide(_frame(), profile)
    assert decision.action == "turn_left"
    assert decision.reason == "wall ahead"


def test_request_carries_frame_prompt_schema_and_options(profile: GameProfile) -> None:
    model, fake = _model(
        lambda _: _reply('{"action": "wait", "reason": "x"}'),
        temperature=0.3,
        context_tokens=2048,
        max_reply_tokens=48,
        keep_alive="5m",
    )
    model.decide(_frame(), profile)

    sent = fake.requests[0]
    assert sent["model"] == "qwen3-vl:2b-instruct"
    assert profile.goal in sent["system"]
    assert sent["format"]["properties"]["action"]["enum"] == profile.action_names
    assert sent["options"] == {"temperature": 0.3, "num_ctx": 2048, "num_predict": 48}
    assert sent["keep_alive"] == "5m"
    image = Image.open(io.BytesIO(base64.b64decode(sent["images"][0])))
    assert image.format == "JPEG"
    assert image.size == (64, 36)
    assert sent["prompt"] == FRAME_PROMPT


def test_history_goes_into_the_prompt_not_the_system_prompt(profile: GameProfile) -> None:
    model, fake = _model(lambda _: _reply('{"action": "turn_left", "reason": "x"}'))
    history = History((PastAction("move_forward", "go", False),) * 3, "move_forward", 3)
    model.decide(_frame(), profile, history)
    sent = fake.requests[0]
    assert sent["prompt"] == build_frame_prompt(history)
    assert "move_forward did nothing 3 times" in sent["prompt"]
    # The system prompt stays identical from call to call.
    assert sent["system"] == build_system_prompt(profile)


def test_timing_is_recorded(profile: GameProfile) -> None:
    model, _ = _model(lambda _: _reply('{"action": "wait", "reason": "x"}'))
    assert model.last_stats is None
    model.decide(_frame(), profile)
    stats = model.last_stats
    assert stats is not None
    assert stats.prompt_tokens == 1128
    assert stats.prompt_seconds == pytest.approx(0.41)
    assert stats.reply_tokens == 22
    assert stats.reply_seconds == pytest.approx(0.1)
    assert stats.total_seconds >= 0


@pytest.mark.parametrize(
    "text",
    [
        "",
        "move forward please",
        '{"reason": "no action key"}',
        '{"action": 42}',
        '{"action": "move_forward"',  # truncated by num_predict
    ],
)
def test_unparseable_reply_becomes_wait(
    profile: GameProfile, text: str, caplog: pytest.LogCaptureFixture
) -> None:
    model, _ = _model(lambda _: _reply(text))
    with caplog.at_level(logging.WARNING):
        decision = model.decide(_frame(), profile)
    assert decision.action == "wait"
    assert "unparseable" in caplog.text


def test_action_outside_profile_becomes_wait(profile: GameProfile) -> None:
    model, _ = _model(lambda _: _reply('{"action": "delete_save", "reason": "chaos"}'))
    assert model.decide(_frame(), profile).action == "wait"


def test_server_error_becomes_wait(profile: GameProfile) -> None:
    model, _ = _model(lambda _: httpx.Response(500, json={"error": "out of memory"}))
    decision = model.decide(_frame(), profile)
    assert decision.action == "wait"
    assert decision.reason is not None and "out of memory" in decision.reason
    assert model.last_stats is not None


def test_timeout_becomes_wait(profile: GameProfile) -> None:
    def slow(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("too slow", request=request)

    model, _ = _model(slow)
    assert model.decide(_frame(), profile).action == "wait"


def test_missing_model_raises_unavailable(profile: GameProfile) -> None:
    model, _ = _model(lambda _: httpx.Response(404, json={"error": "model not found"}))
    with pytest.raises(BrainUnavailableError, match="ollama pull qwen3-vl:2b-instruct"):
        model.decide(_frame(), profile)


def test_server_down_raises_unavailable(profile: GameProfile) -> None:
    def refused(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    model, _ = _model(refused)
    with pytest.raises(BrainUnavailableError, match="Failed to connect to Ollama"):
        model.decide(_frame(), profile)


def test_warm_up_with_a_profile_makes_one_throwaway_decision(profile: GameProfile) -> None:
    # Regression: after a text-only load, a freshly pulled 4B / 7B model took over 10 s on
    # its first real decisions (Phase 5), timing out the start of a run.
    model, fake = _model(lambda _: _reply(OK_REPLY), keep_alive="15m", max_reply_tokens=48)
    model.warm_up(profile)
    (sent,) = fake.requests
    assert sent["model"] == "qwen3-vl:2b-instruct"
    assert sent["keep_alive"] == "15m"
    # Exactly what a decision sends: same system prompt, reply format and options.
    assert sent["system"] == build_system_prompt(profile)
    assert sent["format"]["properties"]["action"]["enum"] == profile.action_names
    assert sent["options"]["num_predict"] == 48
    image = Image.open(io.BytesIO(base64.b64decode(sent["images"][0])))
    assert image.size == (640, 360)  # the usual capture size
    assert model.last_stats is None  # a throwaway: not counted as a decision


def test_warm_up_without_a_profile_just_loads() -> None:
    model, fake = _model(lambda _: _reply(""), keep_alive="15m")
    model.warm_up()
    assert fake.requests == [
        {"model": "qwen3-vl:2b-instruct", "stream": False, "keep_alive": "15m"}
    ]


def test_warm_up_reports_missing_model() -> None:
    model, _ = _model(lambda _: httpx.Response(404, json={"error": "model not found"}))
    with pytest.raises(BrainUnavailableError, match="not installed"):
        model.warm_up()


def test_encode_jpeg_round_trips_size() -> None:
    data = encode_jpeg(_frame())
    assert data[:2] == b"\xff\xd8"  # JPEG magic
    assert Image.open(io.BytesIO(data)).size == (64, 36)


OK_REPLY = '{"action": "interact", "reason": "door"}'


def _raises(error: type[httpx.TransportError]) -> Handler:
    def handler(request: httpx.Request) -> httpx.Response:
        raise error("simulated", request=request)

    return handler


# 1. warm-up: longer timeout, and a timeout is fatal rather than a wait


def test_warm_up_uses_its_own_longer_timeout(profile: GameProfile) -> None:
    model, fake = _model(lambda _: _reply(OK_REPLY), timeout_seconds=10, warm_up_timeout_seconds=90)
    model.warm_up()
    model.decide(_frame(), profile)
    assert fake.read_timeouts == [90, 10]


def test_warm_up_timeout_raises_unavailable() -> None:
    model, _ = _model(_raises(httpx.ReadTimeout), warm_up_timeout_seconds=5)
    with pytest.raises(BrainUnavailableError, match="did not load within 5"):
        model.warm_up()


def test_warm_up_dropped_connection_raises_unavailable() -> None:
    model, _ = _model(_raises(httpx.RemoteProtocolError))
    with pytest.raises(BrainUnavailableError, match="dropped the connection"):
        model.warm_up()


# 2. Ollama crashing or OOMing mid-reply is a wait, not a crash


@pytest.mark.parametrize("error", [httpx.ReadError, httpx.RemoteProtocolError, httpx.WriteError])
def test_transport_error_mid_reply_becomes_wait(
    profile: GameProfile, error: type[httpx.TransportError]
) -> None:
    model, _ = _model(_raises(error))
    decision = model.decide(_frame(), profile)
    assert decision.action == "wait"
    assert decision.reason is not None and error.__name__ in decision.reason


# 3. Consecutive failures stop the loop instead of waiting forever


def test_consecutive_failures_raise_after_the_limit(profile: GameProfile) -> None:
    model, _ = _model(
        lambda _: httpx.Response(500, json={"error": "cuda oom"}), max_consecutive_failures=3
    )
    assert model.decide(_frame(), profile).action == "wait"
    assert model.decide(_frame(), profile).action == "wait"
    with pytest.raises(BrainUnavailableError, match=r"3 decisions in a row failed.*cuda oom"):
        model.decide(_frame(), profile)


def test_unparseable_replies_count_as_failures(profile: GameProfile) -> None:
    model, _ = _model(lambda _: _reply("garbage"), max_consecutive_failures=2)
    assert model.decide(_frame(), profile).action == "wait"
    with pytest.raises(BrainUnavailableError, match="unparseable"):
        model.decide(_frame(), profile)


def test_a_good_decision_resets_the_failure_count(profile: GameProfile) -> None:
    replies = iter(["bad", "bad", OK_REPLY, "bad", "bad", OK_REPLY])
    model, _ = _model(lambda _: _reply(next(replies)), max_consecutive_failures=3)
    actions = [model.decide(_frame(), profile).action for _ in range(6)]
    assert actions == ["wait", "wait", "interact", "wait", "wait", "interact"]


# 4. Unload frees VRAM at shutdown and never raises


def test_unload_sets_keep_alive_to_zero() -> None:
    model, fake = _model(lambda _: _reply(""))
    model.unload()
    assert fake.requests == [{"model": "qwen3-vl:2b-instruct", "stream": False, "keep_alive": 0}]


@pytest.mark.parametrize(
    "handler",
    [
        _raises(httpx.ConnectError),
        _raises(httpx.ReadTimeout),
        lambda _: httpx.Response(500, json={"error": "boom"}),
    ],
)
def test_unload_never_raises(handler: Handler) -> None:
    model, _ = _model(handler)
    model.unload()
