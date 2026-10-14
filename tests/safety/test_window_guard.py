import pytest

from playertwo.safety import TERMINAL_PROCESSES, WindowGuard
from playertwo.win32 import WindowInfo

NOTEPAD = WindowInfo("Untitled - Notepad", "Notepad.exe")
CMD_TITLE = "C:\\Windows\\System32\\cmd.exe - python  -m playertwo --target-window Notepad"


def _guard(window: WindowInfo, *, title: str = "", process: str = "") -> WindowGuard:
    return WindowGuard(target_window=title, target_process=process, window_provider=lambda: window)


@pytest.mark.parametrize(
    ("title", "window"),
    [
        ("Notepad", NOTEPAD),
        ("notepad", NOTEPAD),
        ("  Notepad ", NOTEPAD),
        ("My Game", WindowInfo("My Game", "game.exe")),
    ],
)
def test_title_target_matches_substring(title: str, window: WindowInfo) -> None:
    assert _guard(window, title=title).game_is_focused()


@pytest.mark.parametrize(
    "window",
    [
        WindowInfo("Command Prompt", "cmd.exe"),
        WindowInfo("", ""),
        WindowInfo("My", "game.exe"),
    ],
)
def test_title_target_rejects_other_windows(window: WindowInfo) -> None:
    assert not _guard(window, title="Notepad").game_is_focused()


@pytest.mark.parametrize("terminal", ["WindowsTerminal.exe", "cmd.exe", "conhost.exe", "pwsh.exe"])
def test_terminal_titled_with_the_command_line_never_matches(terminal: str) -> None:
    # Regression: in the Phase 3 live run the terminal's title contained
    # "--target-window Notepad", matched, and received 5 w's while Liam was alt-tabbed.
    window = WindowInfo(CMD_TITLE, terminal)
    assert not _guard(window, title="Notepad").game_is_focused()
    assert not _guard(window, process=terminal).game_is_focused()


def test_terminal_list_is_lowercase() -> None:
    assert all(name == name.lower() for name in TERMINAL_PROCESSES)


@pytest.mark.parametrize("process", ["notepad.exe", "Notepad.exe", " NOTEPAD.EXE "])
def test_process_target_matches_executable_case_insensitively(process: str) -> None:
    assert _guard(NOTEPAD, process=process).game_is_focused()


def test_process_target_ignores_a_matching_title_in_another_program() -> None:
    browser = WindowInfo("How to use Notepad - Google Chrome", "chrome.exe")
    assert not _guard(browser, process="notepad.exe").game_is_focused()


def test_process_and_title_must_both_match() -> None:
    assert _guard(NOTEPAD, process="notepad.exe", title="Notepad").game_is_focused()
    assert not _guard(NOTEPAD, process="notepad.exe", title="Game").game_is_focused()
    other = WindowInfo("Untitled - Notepad", "notepad2.exe")
    assert not _guard(other, process="notepad.exe", title="Notepad").game_is_focused()


@pytest.mark.parametrize(("title", "process"), [("", ""), ("   ", "  ")])
def test_no_target_never_matches(title: str, process: str) -> None:
    # Fail safe: an unconfigured guard must block input, even though "" is in every title.
    guard = _guard(NOTEPAD, title=title, process=process)
    assert not guard.game_is_focused()
    assert guard.describe() == ""


def test_describe_names_the_targets() -> None:
    guard = _guard(NOTEPAD, title="Notepad", process="Notepad.exe")
    assert guard.describe() == "process notepad.exe and window titled *notepad*"


def test_window_is_read_on_every_check() -> None:
    windows = iter([NOTEPAD, WindowInfo("Command Prompt", "cmd.exe")])
    guard = WindowGuard(target_window="Notepad", window_provider=lambda: next(windows))
    assert guard.game_is_focused()
    assert not guard.game_is_focused()


def test_matches_applies_the_same_rules_to_any_window() -> None:
    # Used to find the game window to capture, not only to check the focused one.
    guard = WindowGuard("PlayerTwo Testbed", "python.exe", window_provider=lambda: NOTEPAD)
    assert guard.matches(WindowInfo("PlayerTwo Testbed", "python.exe"))
    assert not guard.matches(WindowInfo("PlayerTwo Testbed", "WindowsTerminal.exe"))
    assert not guard.matches(WindowInfo("python -m testbed", "python.exe"))
    assert not guard.game_is_focused()
