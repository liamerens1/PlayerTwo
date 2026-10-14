import numpy as np

from playertwo.capture import ChangeDetector


def _frame(value: int) -> np.ndarray:
    return np.full((10, 10, 3), value, dtype=np.uint8)


def test_first_frame_counts_as_changed() -> None:
    assert ChangeDetector(threshold=8).has_changed(_frame(0))


def test_identical_frame_is_not_changed() -> None:
    detector = ChangeDetector(threshold=8)
    detector.has_changed(_frame(100))
    assert not detector.has_changed(_frame(100))


def test_small_change_below_threshold_is_ignored() -> None:
    detector = ChangeDetector(threshold=8)
    detector.has_changed(_frame(100))
    assert not detector.has_changed(_frame(105))


def test_large_change_is_detected_without_uint8_overflow() -> None:
    detector = ChangeDetector(threshold=8)
    detector.has_changed(_frame(250))
    assert detector.has_changed(_frame(10))
