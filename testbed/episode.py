"""One attempt at a level: the clock, the closest approach and how it ended."""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict

from testbed.physics import PlayerState, falling, touching_target
from testbed.world import Layout


class Outcome(StrEnum):
    SUCCESS = "success"
    FELL = "fell"
    TIMEOUT = "timeout"

    @property
    def banner(self) -> str:
        """What the full-screen message says."""
        return {
            Outcome.SUCCESS: "SUCCESS",
            Outcome.FELL: "YOU FELL",
            Outcome.TIMEOUT: "TIME UP",
        }[self]


class EpisodeResult(BaseModel):
    """One line of the results file."""

    model_config = ConfigDict(frozen=True, extra="ignore")

    level: int
    seed: int
    outcome: Outcome
    seconds: float
    closest_distance: float
    """Closest centre-to-centre distance to the target, in world units. Touching it
    happens at 1.75 (face on) to 2.47 (at a corner): half the cube plus the player's radius."""
    episode: int = 0
    tag: str = ""
    finished_at: str = ""


class Episode:
    """Tracks one attempt. Call `update` once per frame the game is running."""

    def __init__(self, layout: Layout) -> None:
        self.layout = layout
        self.elapsed = 0.0
        self.closest = layout.distance_to_target(*layout.start)
        self.outcome: Outcome | None = None

    @property
    def seconds_left(self) -> float:
        return max(0.0, self.layout.timeout_seconds - self.elapsed)

    def update(self, state: PlayerState, dt: float) -> Outcome | None:
        """Advance the clock and check how things stand. Returns the outcome once, the
        frame the episode ends; None while it's still going (or already over)."""
        if self.outcome is not None:
            return None
        self.elapsed += dt
        self.closest = min(self.closest, self.layout.distance_to_target(state.x, state.z))
        if touching_target(self.layout, state):
            self.outcome = Outcome.SUCCESS
        elif falling(self.layout, state):
            self.outcome = Outcome.FELL
        elif self.elapsed >= self.layout.timeout_seconds:
            self.outcome = Outcome.TIMEOUT
        return self.outcome

    def result(self, episode: int = 0, tag: str = "", finished_at: str = "") -> EpisodeResult:
        if self.outcome is None:
            raise RuntimeError("the episode hasn't ended yet")
        return EpisodeResult(
            level=self.layout.level,
            seed=self.layout.seed,
            outcome=self.outcome,
            seconds=round(self.elapsed, 2),
            closest_distance=round(self.closest, 2),
            episode=episode,
            tag=tag,
            finished_at=finished_at,
        )
