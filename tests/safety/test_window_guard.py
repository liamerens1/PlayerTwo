import pytest

from playertwo.safety import WindowGuard


def _guard(target: str, title: str) -> WindowGuard:
    return WindowGuard(target, title_provider=lambda: title)


@pytest.mark.parametrize(
    ("target", "title"),
    [
        ("Notepad", "Untitled - Notepad"),
        ("notepad", "Untitled - Notepad"),
        ("  Notepad ", "Untitled - Notepad"),
        ("My Game", "My Game"),
    ],
)
def test_focused_when_title_contains_target(target: str, title: str) -> None:
    assert _guard(target, title).game_is_focused()


@pytest.mark.parametrize(
    ("target", "title"),
    [
        ("Notepad", "Command Prompt"),
        ("Notepad", ""),
        ("My Game", "My"),
    ],
)
def test_not_focused_when_title_differs(target: str, title: str) -> None:
    assert not _guard(target, title).game_is_focused()


@pytest.mark.parametrize("target", ["", "   "])
def test_empty_target_never_matches(target: str) -> None:
    # Fail safe: an unconfigured guard must block input, even though "" is in every title.
    assert not _guard(target, "Untitled - Notepad").game_is_focused()


def test_title_is_read_on_every_check() -> None:
    titles = iter(["Untitled - Notepad", "Command Prompt"])
    guard = WindowGuard("Notepad", title_provider=lambda: next(titles))
    assert guard.game_is_focused()
    assert not guard.game_is_focused()
