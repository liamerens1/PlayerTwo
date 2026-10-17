import pytest

from playertwo.orchestrator import LoopStats, RunReport


def _report(stats: LoopStats, seconds: float = 120.0) -> RunReport:
    return RunReport.from_stats(
        stats,
        model="qwen3-vl:4b-instruct",
        profile="testbed",
        memory=True,
        act_then_look=True,
        seconds=seconds,
        exit_code=0,
    )


def test_rates_are_per_active_minute() -> None:
    stats = LoopStats(decisions=60, decide_seconds=[1.0] * 60, paused_seconds=60.0)
    report = _report(stats, seconds=120.0)
    assert report.active_seconds == 60.0
    assert report.decisions_per_minute == 60.0  # paused time doesn't count


def test_latency_median_and_p90() -> None:
    times = [0.5, 0.6, 0.7, 0.8, 0.9, 1.0, 1.1, 1.2, 1.3, 3.0]
    report = _report(LoopStats(decisions=10, decide_seconds=times))
    assert report.decide_median_seconds == pytest.approx(0.95)
    assert report.decide_p90_seconds == pytest.approx(1.3)


def test_a_run_without_decisions_still_reports() -> None:
    report = _report(LoopStats(paused_seconds=200.0), seconds=100.0)
    assert report.decisions == 0
    assert report.decide_median_seconds is None
    assert report.active_seconds == 0.0
    assert report.decisions_per_minute == 0.0


def test_report_is_json() -> None:
    report = _report(LoopStats(decisions=1, decide_seconds=[0.7], actions_performed=1))
    restored = RunReport.model_validate_json(report.model_dump_json())
    assert restored == report
    assert restored.model == "qwen3-vl:4b-instruct"
