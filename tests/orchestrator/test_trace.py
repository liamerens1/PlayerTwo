import json
from pathlib import Path

import numpy as np
from PIL import Image

from playertwo.actions import Decision, Sighting
from playertwo.orchestrator import Tracer


def _frame() -> np.ndarray:
    return np.full((36, 64, 3), 200, dtype=np.uint8)


def test_each_decision_saves_its_frame_and_a_json_line(tmp_path: Path) -> None:
    tracer = Tracer(tmp_path / "trace")
    seen = Sighting(visible=True, x=0.62, box=(0.55, 0.3, 0.69, 0.5))
    tracer.record(
        _frame(),
        Decision(action="nudge_right", reason="target slightly right (x=0.62)"),
        mode="steer",
        sighting=seen,
        model_seconds=0.7123,
    )
    tracer.record(_frame(), Decision(action="turn_left", reason="wall"), mode="pick", stuck=True)
    lines = [
        json.loads(line) for line in (tmp_path / "trace" / "trace.jsonl").read_text().splitlines()
    ]
    assert [e["frame"] for e in lines] == ["00001.jpg", "00002.jpg"]
    assert lines[0]["sighting"] == {"visible": True, "x": 0.62, "box": [0.55, 0.3, 0.69, 0.5]}
    assert lines[0]["action"] == "nudge_right" and lines[0]["model_seconds"] == 0.712
    assert "sighting" not in lines[1] and lines[1]["stuck"] is True
    assert Image.open(tmp_path / "trace" / "00001.jpg").size == (64, 36)


def test_a_failed_locate_is_traced_as_null(tmp_path: Path) -> None:
    tracer = Tracer(tmp_path)
    tracer.record(_frame(), Decision.wait("couldn't locate the target"), mode="steer")
    (line,) = (tmp_path / "trace.jsonl").read_text().splitlines()
    assert json.loads(line)["sighting"] is None
