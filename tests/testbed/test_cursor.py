from testbed.cursor import plausible_dx


def test_real_movements_pass_through() -> None:
    assert plausible_dx(306, 1280) == 306  # a PlayerTwo turn after Windows acceleration
    assert plausible_dx(-640, 1280) == -640


def test_impossible_readings_are_ignored() -> None:
    # Seen live: +32000 px while the window was restoring.
    assert plausible_dx(32000, 1280) == 0
    assert plausible_dx(-961, 1280) == 0
    assert plausible_dx(5, 0) == 0  # no client area yet
