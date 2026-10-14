from pathlib import Path

import pytest

from playertwo.actions import GameProfile

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def profile() -> GameProfile:
    return GameProfile.load(ROOT / "profiles" / "simple-walker.yaml")
