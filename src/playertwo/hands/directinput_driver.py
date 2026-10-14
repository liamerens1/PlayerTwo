"""Real input via pydirectinput (DirectInput scan codes). Phase 1."""


class DirectInputDriver:
    """InputDriver backed by pydirectinput. Windows only; imported lazily."""

    def key_down(self, key: str) -> None:
        raise NotImplementedError("Phase 1: feat/capture-input/1")

    def key_up(self, key: str) -> None:
        raise NotImplementedError("Phase 1: feat/capture-input/1")

    def press(self, key: str) -> None:
        raise NotImplementedError("Phase 1: feat/capture-input/1")

    def move_mouse(self, dx: int, dy: int) -> None:
        raise NotImplementedError("Phase 1: feat/capture-input/1")
