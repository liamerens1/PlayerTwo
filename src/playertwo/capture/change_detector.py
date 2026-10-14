"""Decides whether a frame differs enough from the last one to be worth a decision."""

import numpy as np

from playertwo.types import Frame


class ChangeDetector:
    """Mean absolute per-pixel difference against the last accepted frame."""

    def __init__(self, threshold: float) -> None:
        self._threshold = threshold
        self._previous: Frame | None = None

    def has_changed(self, frame: Frame) -> bool:
        """True (and remember the frame) if it differs from the last accepted one."""
        previous = self._previous
        if previous is None or previous.shape != frame.shape:
            self._previous = frame
            return True
        diff = np.abs(frame.astype(np.int16) - previous.astype(np.int16))
        if float(diff.mean()) > self._threshold:
            self._previous = frame
            return True
        return False

    def reset(self) -> None:
        self._previous = None
