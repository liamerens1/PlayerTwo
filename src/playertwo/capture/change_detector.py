"""Decides whether a frame differs enough from the last one to be worth a decision."""

import numpy as np

from playertwo.types import Frame


def frame_difference(a: Frame, b: Frame) -> float:
    """Mean absolute per-pixel difference, 0-255. Frames of different shapes count as
    completely different."""
    if a.shape != b.shape:
        return 255.0
    # int16 so the subtraction can't wrap around like uint8 would.
    return float(np.abs(a.astype(np.int16) - b.astype(np.int16)).mean())


class ChangeDetector:
    """Mean absolute per-pixel difference against the last accepted frame."""

    def __init__(self, threshold: float) -> None:
        self._threshold = threshold
        self._previous: Frame | None = None

    def has_changed(self, frame: Frame) -> bool:
        """True (and remember the frame) if it differs from the last accepted one."""
        previous = self._previous
        if previous is None or frame_difference(frame, previous) > self._threshold:
            self._previous = frame
            return True
        return False

    def reset(self) -> None:
        self._previous = None
