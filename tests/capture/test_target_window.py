from collections.abc import Callable

from playertwo.capture import TargetWindow
from playertwo.capture.target_window import REFIND_SECONDS
from playertwo.types import Rect
from playertwo.win32 import WindowInfo


class FakeDesktop:
    def __init__(self) -> None:
        self.windows: dict[int, tuple[WindowInfo, Rect | None]] = {}
        self.searches = 0
        self.now = 0.0

    def find(self, matches: Callable[[WindowInfo], bool]) -> int | None:
        self.searches += 1
        return next((h for h, (info, _) in self.windows.items() if matches(info)), None)

    def rect_of(self, hwnd: int) -> Rect | None:
        return self.windows[hwnd][1] if hwnd in self.windows else None

    def exists(self, hwnd: int) -> bool:
        return hwnd in self.windows

    def target(self) -> TargetWindow:
        return TargetWindow(
            lambda w: w.title == "PlayerTwo Testbed",
            find=self.find,
            rect_of=self.rect_of,
            exists=self.exists,
            clock=lambda: self.now,
        )


GAME = WindowInfo("PlayerTwo Testbed", "python.exe")


def test_finds_the_window_once_and_follows_moves() -> None:
    desktop = FakeDesktop()
    desktop.windows[7] = (GAME, Rect(0, 0, 1280, 720))
    target = desktop.target()
    assert target.rect() == Rect(0, 0, 1280, 720)
    desktop.windows[7] = (GAME, Rect(100, 50, 1380, 770))  # moved
    assert target.rect() == Rect(100, 50, 1380, 770)
    assert desktop.searches == 1
    assert target.ever_found


def test_missing_window_is_searched_for_at_most_every_refind_interval() -> None:
    desktop = FakeDesktop()
    target = desktop.target()
    assert target.rect() is None
    assert target.rect() is None
    assert desktop.searches == 1
    desktop.windows[3] = (GAME, Rect(0, 0, 10, 10))
    desktop.now += REFIND_SECONDS
    assert target.rect() == Rect(0, 0, 10, 10)
    assert desktop.searches == 2


def test_closed_window_is_noticed_and_a_new_one_found() -> None:
    desktop = FakeDesktop()
    desktop.windows[7] = (GAME, Rect(0, 0, 10, 10))
    target = desktop.target()
    assert target.handle() == 7
    del desktop.windows[7]
    desktop.now += REFIND_SECONDS
    assert target.handle() is None
    desktop.windows[9] = (GAME, Rect(0, 0, 20, 20))
    desktop.now += REFIND_SECONDS
    assert target.handle() == 9


def test_minimised_window_has_no_rect_but_still_exists() -> None:
    desktop = FakeDesktop()
    desktop.windows[7] = (GAME, None)
    target = desktop.target()
    assert target.rect() is None
    assert target.handle() == 7
