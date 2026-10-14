"""Shared type aliases and small value types."""

from typing import NamedTuple

import numpy as np
from numpy.typing import NDArray

Frame = NDArray[np.uint8]
"""One captured screen frame: H x W x 3, RGB, uint8."""


class Rect(NamedTuple):
    """A screen rectangle in pixels. `right` and `bottom` are exclusive."""

    left: int
    top: int
    right: int
    bottom: int

    @property
    def width(self) -> int:
        return self.right - self.left

    @property
    def height(self) -> int:
        return self.bottom - self.top
