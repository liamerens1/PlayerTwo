"""Where on which monitor the game window is: pure maths, no Windows calls."""

from collections.abc import Sequence

from playertwo.types import Rect


def capture_region(window: Rect, outputs: Sequence[Rect]) -> tuple[int, Rect] | None:
    """Pick the output (monitor) showing most of `window` and return its index and the
    window's area relative to that output's top-left corner, clipped to the output.

    `window` and `outputs` are in desktop coordinates, where monitors left of or above
    the primary have negative coordinates. None if the window is on no output at all
    (or has no area). A window straddling two monitors is captured from the one with
    the larger share; the part on the other monitor is cut off.
    """
    best: tuple[int, Rect] | None = None
    best_area = 0
    for index, output in enumerate(outputs):
        left, top = max(window.left, output.left), max(window.top, output.top)
        right, bottom = min(window.right, output.right), min(window.bottom, output.bottom)
        if right <= left or bottom <= top:
            continue
        area = (right - left) * (bottom - top)
        if area > best_area:
            best_area = area
            best = (
                index,
                Rect(
                    left - output.left, top - output.top, right - output.left, bottom - output.top
                ),
            )
    return best
