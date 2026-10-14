import threading
import time

from playertwo.orchestrator import Latest


def test_take_returns_none_after_timeout_when_empty() -> None:
    slot: Latest[int] = Latest()
    start = time.monotonic()
    assert slot.take(timeout=0.05) is None
    assert time.monotonic() - start >= 0.04


def test_put_then_take_removes_the_value() -> None:
    slot: Latest[int] = Latest()
    slot.put(1)
    assert slot.take(timeout=0) == 1
    assert slot.take(timeout=0) is None


def test_only_the_newest_value_survives() -> None:
    slot: Latest[int] = Latest()
    for value in range(5):
        slot.put(value)
    assert slot.take(timeout=0) == 4
    assert slot.replaced == 4


def test_take_wakes_up_when_a_value_arrives() -> None:
    slot: Latest[str] = Latest()
    threading.Timer(0.05, slot.put, args=("frame",)).start()
    start = time.monotonic()
    assert slot.take(timeout=2) == "frame"
    assert time.monotonic() - start < 1
