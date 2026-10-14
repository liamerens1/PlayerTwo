"""Results files (one JSON line per episode) and their summary."""

import statistics
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from testbed.episode import EpisodeResult, Outcome

RESULTS_DIR = Path(__file__).resolve().parent / "results"


def new_results_path(directory: Path = RESULTS_DIR, now: datetime | None = None) -> Path:
    stamp = (now or datetime.now()).strftime("%Y%m%d-%H%M%S")
    return directory / f"{stamp}.jsonl"


class ResultsLog:
    """Appends one line per finished episode, flushed immediately, so a crash or a closed
    window never loses the episodes already played."""

    def __init__(self, path: Path) -> None:
        self.path = path

    def append(self, result: EpisodeResult) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as f:
            f.write(result.model_dump_json() + "\n")


def load_results(path: Path) -> list[EpisodeResult]:
    lines = path.read_text(encoding="utf-8").splitlines()
    return [EpisodeResult.model_validate_json(line) for line in lines if line.strip()]


@dataclass(frozen=True)
class LevelSummary:
    tag: str
    level: int
    episodes: int
    successes: int
    fell: int
    timeouts: int
    median_success_seconds: float | None
    median_closest_distance: float

    @property
    def success_rate(self) -> float:
        return self.successes / self.episodes if self.episodes else 0.0


def summarise(results: Iterable[EpisodeResult]) -> list[LevelSummary]:
    """Per (tag, level): success rate, median time to success, deaths and timeouts."""
    groups: dict[tuple[str, int], list[EpisodeResult]] = {}
    for result in results:
        groups.setdefault((result.tag, result.level), []).append(result)
    summaries = []
    for (tag, level), group in sorted(groups.items()):
        wins = [r.seconds for r in group if r.outcome is Outcome.SUCCESS]
        summaries.append(
            LevelSummary(
                tag=tag,
                level=level,
                episodes=len(group),
                successes=len(wins),
                fell=sum(r.outcome is Outcome.FELL for r in group),
                timeouts=sum(r.outcome is Outcome.TIMEOUT for r in group),
                median_success_seconds=statistics.median(wins) if wins else None,
                median_closest_distance=statistics.median(r.closest_distance for r in group),
            )
        )
    return summaries


def format_summary(summaries: list[LevelSummary]) -> str:
    width = max([3, *(len(s.tag or "-") for s in summaries)])
    header = (
        f"{'tag':<{width}} {'level':>5} {'episodes':>8} {'success':>8} {'rate':>6} "
        f"{'median time':>11} {'fell':>5} {'time up':>7} {'median closest':>14}"
    )
    rows = [header, "-" * len(header)]
    for s in summaries:
        median_time = (
            f"{s.median_success_seconds:.1f} s" if s.median_success_seconds is not None else "-"
        )
        rows.append(
            f"{s.tag or '-':<{width}} {s.level:>5} {s.episodes:>8} {s.successes:>8} "
            f"{s.success_rate:>6.0%} {median_time:>11} {s.fell:>5} {s.timeouts:>7} "
            f"{s.median_closest_distance:>14.2f}"
        )
    return "\n".join(rows)
