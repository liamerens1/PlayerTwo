import logging
from pathlib import Path
from typing import ClassVar

import pytest

from playertwo import app
from playertwo.app import EXIT_INVALID_CONFIG, EXIT_NO_TARGET, EXIT_OK, main

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def _repo_root(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(ROOT)


def test_check_validates_and_exits(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["--check"]) == EXIT_OK
    assert "Profile OK" in capsys.readouterr().out


def test_refuses_to_play_without_a_target_window(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # Its own config with an explicitly empty target, so a locally edited config.yaml can
    # never make this test start the real loop and send input.
    config = tmp_path / "config.yaml"
    profile = (ROOT / "profiles" / "simple-walker.yaml").as_posix()
    config.write_text(
        f"profile: {profile}\nsafety:\n  target_window: ''\n  target_process: ''\n",
        encoding="utf-8",
    )
    assert main(["--config", str(config)]) == EXIT_NO_TARGET
    assert "No target" in capsys.readouterr().out


def test_bad_config_path_is_reported() -> None:
    assert main(["--config", "does/not/exist.yaml"]) == EXIT_INVALID_CONFIG


def test_http_request_logs_are_quiet_at_info() -> None:
    # One INFO line per decision from httpx drowned the terminal in the first live run.
    main(["--check"])
    assert logging.getLogger("httpx").getEffectiveLevel() >= logging.WARNING


def test_profile_and_memory_flags(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["--check", "--profile", "profiles/testbed.yaml", "--no-memory"]) == EXIT_OK
    out = capsys.readouterr().out
    assert "memory=off" in out
    assert "Profile OK testbed: move_forward, turn_left, turn_right, wait" in out


class FakeModel:
    """Stands in for OllamaVisionModel: no Ollama needed, records unload."""

    instances: ClassVar[list["FakeModel"]] = []

    def __init__(self, settings: object) -> None:
        self.unloaded = False
        FakeModel.instances.append(self)

    def warm_up(self, profile: object = None) -> None:
        pass

    def unload(self) -> None:
        self.unloaded = True


@pytest.mark.parametrize("broken", ["DxcamFrameSource", "KillSwitch"])
def test_model_is_unloaded_when_setup_fails_after_warm_up(
    broken: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Phase 3 review: building capture or the kill switch could fail after the model was
    # loaded, leaving it in VRAM the game needs. Nothing here can send input: setup fails
    # before the executor exists.
    def fail(*args: object, **kwargs: object) -> None:
        raise RuntimeError(f"{broken} failed")

    FakeModel.instances.clear()
    monkeypatch.setattr(app, "OllamaVisionModel", FakeModel)
    monkeypatch.setattr(app, broken, fail)
    with pytest.raises(RuntimeError, match=f"{broken} failed"):
        main(["--target-process", "no-such-game.exe"])
    (model,) = FakeModel.instances
    assert model.unloaded


def test_model_override_is_shown_and_validated(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["--check", "--model", "qwen3-vl:4b-instruct"]) == EXIT_OK
    assert "model=qwen3-vl:4b-instruct" in capsys.readouterr().out
    # Overrides go through the same validation as the config file: no cloud models.
    assert main(["--check", "--model", "qwen3-vl:235b-cloud"]) == EXIT_INVALID_CONFIG
    assert "not a local model" in capsys.readouterr().out


def test_steering_is_on_for_a_profile_with_a_target(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["--check", "--profile", "profiles/testbed.yaml"]) == EXIT_OK
    assert "steer=on" in capsys.readouterr().out
    assert main(["--check", "--profile", "profiles/testbed.yaml", "--no-steer"]) == EXIT_OK
    assert "steer=off" in capsys.readouterr().out
    assert main(["--check"]) == EXIT_OK  # simple-walker has no target
    assert "steer=off" in capsys.readouterr().out
