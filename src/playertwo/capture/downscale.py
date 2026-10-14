"""Shrinking frames before the model sees them."""

import numpy as np
from PIL import Image

from playertwo.types import Frame


def downscale_to_width(frame: Frame, width: int) -> Frame:
    """Resize to `width` pixels wide, keeping aspect ratio. Never upscales."""
    height, current_width = frame.shape[:2]
    if current_width <= width:
        return frame
    new_height = max(1, round(height * width / current_width))
    resized = Image.fromarray(frame).resize((width, new_height), Image.Resampling.BILINEAR)
    return np.asarray(resized, dtype=np.uint8)
