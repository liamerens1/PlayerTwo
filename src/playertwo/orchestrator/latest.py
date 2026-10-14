"""Single-slot hand-offs between threads: only the newest value is ever kept."""

import threading


class Latest[T]:
    """Holds at most one value. `put` replaces whatever is there; `take` removes it.

    A backlog of stale frames or actions is worse than none, so nothing ever queues.
    """

    def __init__(self) -> None:
        self._value: T | None = None
        self._condition = threading.Condition()
        self.replaced = 0
        """How many values were overwritten before anyone took them."""

    def put(self, value: T) -> None:
        with self._condition:
            if self._value is not None:
                self.replaced += 1
            self._value = value
            self._condition.notify_all()

    def clear(self) -> None:
        """Drop the waiting value, if any."""
        with self._condition:
            self._value = None

    def take(self, timeout: float) -> T | None:
        """The newest value, or None if nothing arrives within `timeout` seconds."""
        with self._condition:
            if self._value is None:
                self._condition.wait(timeout)
            value, self._value = self._value, None
            return value


class Current[T]:
    """The most recent value, read without removing it (unlike `Latest.take`)."""

    def __init__(self) -> None:
        self._value: T | None = None
        self._lock = threading.Lock()

    def set(self, value: T) -> None:
        with self._lock:
            self._value = value

    def get(self) -> T | None:
        with self._lock:
            return self._value

    def clear(self) -> None:
        with self._lock:
            self._value = None
