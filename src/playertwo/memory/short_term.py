"""Tier 1 short-term memory: the last few performed actions and a stuck detector."""

import threading
from collections import deque
from collections.abc import Sequence

from playertwo.actions import History, PastAction

REASON_MAX_CHARS = 40
"""Reasons are cut to this in the history, to keep the prompt short for small models."""


def detect_stuck(recent: Sequence[PastAction], repeats: int) -> tuple[str, int] | None:
    """(action, times) if the last `repeats` or more actions that can move anything
    (waits are skipped) were the same action and none of them changed the screen."""
    moves = [past for past in recent if past.screen_changed is not None]
    if not moves:
        return None
    action = moves[-1].action
    run = 0
    for past in reversed(moves):
        if past.action != action or past.screen_changed:
            break
        run += 1
    return (action, run) if run >= repeats else None


class ShortTermMemory:
    """A ring of the last `size` performed actions. Thread-safe: hands records, the brain
    takes snapshots."""

    def __init__(self, size: int = 8, stuck_repeats: int = 3) -> None:
        self._recent: deque[PastAction] = deque(maxlen=size)
        self._stuck_repeats = stuck_repeats
        self._lock = threading.Lock()

    def record(self, action: str, reason: str | None, screen_changed: bool | None) -> None:
        reason = " ".join((reason or "").split())
        if len(reason) > REASON_MAX_CHARS:
            reason = reason[: REASON_MAX_CHARS - 3].rstrip() + "..."
        with self._lock:
            self._recent.append(PastAction(action, reason, screen_changed))

    def snapshot(self) -> History:
        with self._lock:
            recent = tuple(self._recent)
        stuck = detect_stuck(recent, self._stuck_repeats)
        if stuck is None:
            return History(recent)
        return History(recent, stuck_action=stuck[0], stuck_repeats=stuck[1])

    def clear(self) -> None:
        with self._lock:
            self._recent.clear()
