import pytest
from pydantic import ValidationError

from playertwo.config import SafetySettings


@pytest.mark.parametrize(
    ("raw", "expected"), [("f12", "f12"), (" F12 ", "f12"), ("pause", "pause")]
)
def test_kill_switch_accepts_a_single_key(raw: str, expected: str) -> None:
    assert SafetySettings(kill_switch=raw).kill_switch == expected


@pytest.mark.parametrize("raw", ["", "  ", "ctrl+f12", "f12, f11"])
def test_kill_switch_rejects_combos_and_blanks(raw: str) -> None:
    with pytest.raises(ValidationError, match="single key"):
        SafetySettings(kill_switch=raw)
