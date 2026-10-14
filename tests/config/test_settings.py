import pytest
from pydantic import ValidationError

from playertwo.config import BrainSettings, SafetySettings


@pytest.mark.parametrize(
    ("raw", "expected"), [("f12", "f12"), (" F12 ", "f12"), ("pause", "pause")]
)
def test_kill_switch_accepts_a_single_key(raw: str, expected: str) -> None:
    assert SafetySettings(kill_switch=raw).kill_switch == expected


@pytest.mark.parametrize("raw", ["", "  ", "ctrl+f12", "f12, f11"])
def test_kill_switch_rejects_combos_and_blanks(raw: str) -> None:
    with pytest.raises(ValidationError, match="single key"):
        SafetySettings(kill_switch=raw)


@pytest.mark.parametrize(
    "model", ["qwen3-vl:2b-instruct", "qwen2.5vl:7b", "moondream", "my-cloudy-model:latest"]
)
def test_local_models_are_allowed(model: str) -> None:
    assert BrainSettings(model=model).model == model


@pytest.mark.parametrize(
    "model", ["gpt-oss:120b-cloud", "qwen3-vl:235b-cloud", "glm-4.6:cloud", "", "  "]
)
def test_cloud_models_are_rejected(model: str) -> None:
    with pytest.raises(ValidationError):
        BrainSettings(model=model)


@pytest.mark.parametrize(
    "host", ["http://localhost:11434", "http://127.0.0.1:11434", "http://[::1]:11434"]
)
def test_loopback_hosts_are_allowed(host: str) -> None:
    assert BrainSettings(host=host).host == host


@pytest.mark.parametrize(
    "host", ["https://ollama.com", "http://192.168.1.20:11434", "http://my-pc:11434", "localhost"]
)
def test_remote_hosts_are_rejected(host: str) -> None:
    with pytest.raises(ValidationError, match="this machine"):
        BrainSettings(host=host)
