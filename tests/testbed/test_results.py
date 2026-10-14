import json
from datetime import datetime
from pathlib import Path

import pytest

from testbed.episode import EpisodeResult, Outcome
from testbed.results import (
    ResultsLog,
    format_summary,
    load_results,
    new_results_path,
    summarise,
)


def _result(
    level: int, outcome: Outcome, seconds: float, closest: float, tag: str = ""
) -> EpisodeResult:
    return EpisodeResult(
        level=level, seed=1, outcome=outcome, seconds=seconds, closest_distance=closest, tag=tag
    )


def test_results_path_is_timestamped(tmp_path: Path) -> None:
    path = new_results_path(tmp_path, now=datetime(2026, 10, 14, 15, 30, 5))
    assert path == tmp_path / "20261014-153005.jsonl"


def test_log_appends_one_json_line_per_episode(tmp_path: Path) -> None:
    path = tmp_path / "sub" / "run.jsonl"
    log = ResultsLog(path)
    log.append(_result(1, Outcome.SUCCESS, 4.2, 1.8))
    log.append(_result(1, Outcome.TIMEOUT, 30.0, 6.5))
    lines = path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    first = json.loads(lines[0])
    assert first["level"] == 1 and first["outcome"] == "success" and first["seconds"] == 4.2
    assert first["closest_distance"] == 1.8
    assert load_results(path)[1].outcome is Outcome.TIMEOUT


def test_summary_per_level() -> None:
    results = [
        _result(1, Outcome.SUCCESS, 4.0, 1.8),
        _result(1, Outcome.SUCCESS, 6.0, 1.9),
        _result(1, Outcome.SUCCESS, 9.0, 2.0),
        _result(1, Outcome.TIMEOUT, 30.0, 7.0),
        _result(5, Outcome.FELL, 3.0, 9.0),
        _result(5, Outcome.SUCCESS, 12.0, 2.1),
    ]
    one, five = summarise(results)
    assert (one.level, one.episodes, one.successes, one.fell, one.timeouts) == (1, 4, 3, 0, 1)
    assert one.success_rate == pytest.approx(0.75)
    assert one.median_success_seconds == 6.0
    assert one.median_closest_distance == pytest.approx(1.95)
    assert (five.level, five.successes, five.fell, five.timeouts) == (5, 1, 1, 0)


def test_summary_separates_tags_and_handles_no_successes() -> None:
    results = [
        _result(1, Outcome.TIMEOUT, 30.0, 7.0, tag="no-memory"),
        _result(1, Outcome.SUCCESS, 5.0, 1.8, tag="memory"),
    ]
    memory, no_memory = summarise(results)
    assert memory.tag == "memory" and memory.success_rate == 1.0
    assert no_memory.median_success_seconds is None
    table = format_summary([memory, no_memory])
    assert "memory" in table and "100%" in table and "0%" in table
