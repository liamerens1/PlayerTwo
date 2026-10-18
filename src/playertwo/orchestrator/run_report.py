"""A machine-readable summary of one run, for comparing models and settings."""

import statistics

from pydantic import BaseModel, ConfigDict

from playertwo.orchestrator.game_loop import LoopStats


def _percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, round(fraction * (len(ordered) - 1)))]


class RunReport(BaseModel):
    """What `python -m playertwo --stats-json PATH` writes when it stops."""

    model_config = ConfigDict(frozen=True)

    model: str
    profile: str
    memory: bool
    act_then_look: bool
    steer: bool = False
    """Look, then steer: the model located the target and code picked the actions."""
    seconds: float
    """Wall-clock time the loop ran."""
    active_seconds: float
    """`seconds` minus the time spent paused because the game wasn't focused."""
    decisions: int
    decide_median_seconds: float | None
    decide_p90_seconds: float | None
    decisions_per_minute: float
    """Per active minute. With act-then-look this includes the time actions take."""
    actions_performed: int
    dropped_stale: int
    dropped_by_gate: int
    stuck_hints: int
    steered: int = 0
    target_seen: int = 0
    exit_code: int

    @classmethod
    def from_stats(
        cls,
        stats: LoopStats,
        *,
        model: str,
        profile: str,
        memory: bool,
        act_then_look: bool,
        seconds: float,
        steer: bool = False,
        exit_code: int,
    ) -> "RunReport":
        active = max(0.0, seconds - stats.paused_seconds)
        times = stats.decide_seconds
        return cls(
            model=model,
            profile=profile,
            memory=memory,
            act_then_look=act_then_look,
            steer=steer,
            seconds=round(seconds, 2),
            active_seconds=round(active, 2),
            decisions=stats.decisions,
            decide_median_seconds=round(statistics.median(times), 3) if times else None,
            decide_p90_seconds=round(_percentile(times, 0.9), 3) if times else None,
            decisions_per_minute=round(stats.decisions * 60 / active, 1) if active else 0.0,
            actions_performed=stats.actions_performed,
            dropped_stale=stats.dropped_stale,
            dropped_by_gate=stats.dropped_by_gate,
            stuck_hints=stats.stuck_hints,
            steered=stats.steered,
            target_seen=stats.target_seen,
            exit_code=exit_code,
        )
