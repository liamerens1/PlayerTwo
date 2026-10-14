import sys
from types import ModuleType

import pytest

from playertwo.hands import DirectInputDriver


class FakePyDirectInput(ModuleType):
    """Stands in for pydirectinput so these tests never send real input."""

    def __init__(self) -> None:
        super().__init__("pydirectinput")
        self.PAUSE = 0.1
        self.FAILSAFE = True
        self.KEYBOARD_MAPPING: dict[str, int | None] = {"w": 0x11, "e": 0x12, "nokey": None}
        self.calls: list[tuple[object, ...]] = []

    def keyDown(self, key: str) -> None:  # noqa: N802 - mirrors pydirectinput's API
        self.calls.append(("keyDown", key))

    def keyUp(self, key: str) -> None:  # noqa: N802
        self.calls.append(("keyUp", key))

    def press(self, key: str) -> None:
        self.calls.append(("press", key))

    def moveRel(self, dx: int, dy: int, *, relative: bool) -> None:  # noqa: N802
        self.calls.append(("moveRel", dx, dy, relative))


@pytest.fixture
def fake_pdi(monkeypatch: pytest.MonkeyPatch) -> FakePyDirectInput:
    fake = FakePyDirectInput()
    monkeypatch.setitem(sys.modules, "pydirectinput", fake)
    return fake


def test_constructor_disables_pause_and_corner_failsafe(fake_pdi: FakePyDirectInput) -> None:
    DirectInputDriver()
    assert fake_pdi.PAUSE == 0
    assert fake_pdi.FAILSAFE is False


def test_calls_map_to_pydirectinput(fake_pdi: FakePyDirectInput) -> None:
    driver = DirectInputDriver()
    driver.key_down("w")
    driver.key_up("w")
    driver.press("e")
    driver.move_mouse(-150, 20)
    assert fake_pdi.calls == [
        ("keyDown", "w"),
        ("keyUp", "w"),
        ("press", "e"),
        ("moveRel", -150, 20, True),
    ]


@pytest.mark.parametrize("key", ["not_a_key", "nokey"])
def test_unknown_key_raises_instead_of_silently_doing_nothing(
    fake_pdi: FakePyDirectInput, key: str
) -> None:
    driver = DirectInputDriver()
    with pytest.raises(ValueError, match="no scan code"):
        driver.key_down(key)
    assert fake_pdi.calls == []
