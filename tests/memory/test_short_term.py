import threading

from playertwo.actions import PastAction
from playertwo.memory import REASON_MAX_CHARS, ShortTermMemory, detect_stuck


def _moves(*entries: tuple[str, bool | None]) -> list[PastAction]:
    return [PastAction(action, "", changed) for action, changed in entries]


def test_keeps_only_the_last_size_actions_oldest_first() -> None:
    memory = ShortTermMemory(size=3)
    for i in range(5):
        memory.record("move_forward", f"step {i}", True)
    assert [p.reason for p in memory.snapshot().recent] == ["step 2", "step 3", "step 4"]


def test_reasons_are_shortened_and_tidied() -> None:
    memory = ShortTermMemory()
    memory.record(
        "turn_left", "  the cube is\nsomewhere to the left of the big purple wall  ", True
    )
    memory.record("wait", None, None)
    long_reason, empty = (p.reason for p in memory.snapshot().recent)
    assert len(long_reason) <= REASON_MAX_CHARS and long_reason.endswith("...")
    assert "\n" not in long_reason and not long_reason.startswith(" ")
    assert empty == ""


def test_not_stuck_while_the_screen_changes() -> None:
    assert detect_stuck(_moves(("move_forward", True)) * 5, repeats=3) is None


def test_stuck_after_repeats_without_change() -> None:
    recent = _moves(("turn_left", True), *[("move_forward", False)] * 3)
    assert detect_stuck(recent, repeats=3) == ("move_forward", 3)
    assert detect_stuck(recent, repeats=4) is None


def test_waits_are_ignored_by_the_stuck_detector() -> None:
    recent = _moves(("move_forward", False), ("wait", None), ("move_forward", False))
    assert detect_stuck(recent, repeats=2) == ("move_forward", 2)


def test_a_different_action_or_a_change_breaks_the_run() -> None:
    assert detect_stuck(_moves(("move_forward", False), ("turn_left", False)), 2) is None
    changed_last = _moves(("move_forward", False), ("move_forward", True))
    assert detect_stuck(changed_last, 2) is None
    assert detect_stuck([], 2) is None


def test_snapshot_carries_the_stuck_verdict() -> None:
    memory = ShortTermMemory(size=8, stuck_repeats=2)
    memory.record("move_forward", "go", False)
    assert memory.snapshot().stuck_action is None
    memory.record("move_forward", "go", False)
    history = memory.snapshot()
    assert (history.stuck_action, history.stuck_repeats) == ("move_forward", 2)
    memory.clear()
    assert memory.snapshot().recent == ()


def test_record_and_snapshot_from_two_threads() -> None:
    memory = ShortTermMemory(size=8)

    def writer() -> None:
        for _ in range(2000):
            memory.record("move_forward", "x", True)

    thread = threading.Thread(target=writer)
    thread.start()
    while thread.is_alive():
        assert len(memory.snapshot().recent) <= 8
    thread.join()
