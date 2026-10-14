from playertwo.capture import capture_region
from playertwo.types import Rect

PRIMARY = Rect(0, 0, 1920, 1080)
LEFT = Rect(-2560, -360, 0, 1080)  # a bigger monitor left of the primary, top higher
RIGHT = Rect(1920, 0, 3840, 1080)


def test_window_on_the_primary_monitor() -> None:
    assert capture_region(Rect(320, 180, 1600, 900), [PRIMARY]) == (
        0,
        Rect(320, 180, 1600, 900),
    )


def test_region_is_relative_to_its_monitor_with_negative_desktop_coordinates() -> None:
    window = Rect(-2000, -200, -720, 520)
    assert capture_region(window, [PRIMARY, LEFT]) == (1, Rect(560, 160, 1840, 880))


def test_output_index_follows_the_given_order() -> None:
    window = Rect(2000, 100, 3280, 820)
    assert capture_region(window, [RIGHT, PRIMARY]) == (0, Rect(80, 100, 1360, 820))
    assert capture_region(window, [PRIMARY, RIGHT]) == (1, Rect(80, 100, 1360, 820))


def test_window_straddling_two_monitors_uses_the_larger_share_and_is_clipped() -> None:
    window = Rect(1500, 100, 2780, 820)  # 420 px on the primary, 860 px on the right
    assert capture_region(window, [PRIMARY, RIGHT]) == (1, Rect(0, 100, 860, 820))


def test_window_partly_off_screen_is_clipped() -> None:
    assert capture_region(Rect(-100, 900, 500, 1300), [PRIMARY]) == (0, Rect(0, 900, 500, 1080))


def test_window_on_no_monitor_or_without_area() -> None:
    assert capture_region(Rect(5000, 0, 6000, 500), [PRIMARY]) is None
    assert capture_region(Rect(100, 100, 100, 500), [PRIMARY]) is None
    assert capture_region(Rect(0, 0, 100, 100), []) is None
