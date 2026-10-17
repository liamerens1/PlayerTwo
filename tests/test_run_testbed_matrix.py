"""The pure parts of scripts/run_testbed_matrix.py (nothing here starts a process)."""

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

from testbed.episode import EpisodeResult, Outcome

ROOT = Path(__file__).resolve().parents[1]


def _matrix() -> ModuleType:
    path = ROOT / "scripts" / "run_testbed_matrix.py"
    spec = importlib.util.spec_from_file_location("run_testbed_matrix", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["run_testbed_matrix"] = module  # dataclasses look their module up
    spec.loader.exec_module(module)
    return module


matrix = _matrix()


def _result(outcome: Outcome, seconds: float) -> EpisodeResult:
    return EpisodeResult(level=2, seed=1, outcome=outcome, seconds=seconds, closest_distance=2.0)


def test_plan_covers_every_combination_grouped_by_model() -> None:
    combos = matrix.plan(["a:2b", "b:7b"], [1, 2], "both")
    assert len(combos) == 8
    assert [c.model for c in combos] == ["a:2b"] * 4 + ["b:7b"] * 4
    assert matrix.plan(["a:2b"], [2], "off") == [matrix.Combo("a:2b", 2, False)]


def test_tags_and_file_names() -> None:
    combo = matrix.Combo("qwen3-vl:4b-instruct", 2, True)
    assert combo.tag == "qwen3-vl:4b-instruct L2 mem-on"
    assert combo.slug == "qwen3-vl_4b-instruct-l2-mem-on"
    assert ":" not in combo.slug and "/" not in combo.slug


def test_matrix_table_row() -> None:
    outcome = matrix.RunOutcome(
        combo=matrix.Combo("qwen2.5vl:7b", 2, False),
        results=[
            _result(Outcome.SUCCESS, 8.0),
            _result(Outcome.SUCCESS, 12.0),
            _result(Outcome.TIMEOUT, 40.0),
            _result(Outcome.FELL, 3.0),
        ],
        report={"decide_median_seconds": 2.25, "decisions_per_minute": 21.5},
        gpu_baseline_mib=1100,
        gpu_peak_mib=7400,
    )
    row = matrix.format_matrix([outcome]).splitlines()[-1]
    cells = [cell.strip() for cell in row.strip("|").split("|")]
    assert cells == [
        "qwen2.5vl:7b",
        "2",
        "off",
        "2/4",
        "10.0 s",
        "1",
        "1",
        "2.25 s",
        "21.5",
        "7400",
        "6300",
    ]


def test_matrix_row_without_report_or_gpu() -> None:
    outcome = matrix.RunOutcome(
        combo=matrix.Combo("m:1", 1, True),
        results=[_result(Outcome.TIMEOUT, 30.0)],
        report=None,
        gpu_baseline_mib=None,
        gpu_peak_mib=None,
    )
    row = matrix.format_matrix([outcome]).splitlines()[-1]
    assert "0/1" in row and row.count("| - ") >= 4
