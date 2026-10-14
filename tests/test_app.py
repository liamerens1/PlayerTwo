import logging
from pathlib import Path

import pytest

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
