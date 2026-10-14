"""Shared type aliases."""

import numpy as np
from numpy.typing import NDArray

Frame = NDArray[np.uint8]
"""One captured screen frame: H x W x 3, RGB, uint8."""
