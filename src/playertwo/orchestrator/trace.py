"""--trace: save every frame the model looked at and what came of it, for debugging."""

import json
import threading
import time
from pathlib import Path

from PIL import Image

from playertwo.actions import Decision, Sighting
from playertwo.types import Frame

TRACE_JPEG_QUALITY = 80


class Tracer:
    """Writes `NNNNN.jpg` (the frame decided on) and one line per decision to
    `trace.jsonl` in `directory`: time, mode (steer or pick), what the model saw, the
    action and its reason, and how long the model took. Called by the brain thread."""

    def __init__(self, directory: Path) -> None:
        self.directory = directory
        directory.mkdir(parents=True, exist_ok=True)
        self._log = directory / "trace.jsonl"
        self._start = time.monotonic()
        self._count = 0
        self._lock = threading.Lock()

    def record(
        self,
        frame: Frame,
        decision: Decision,
        *,
        mode: str,
        sighting: Sighting | None = None,
        model_seconds: float | None = None,
        stuck: bool = False,
    ) -> None:
        with self._lock:
            self._count += 1
            index = self._count
        name = f"{index:05d}.jpg"
        Image.fromarray(frame).save(self.directory / name, quality=TRACE_JPEG_QUALITY)
        entry: dict[str, object] = {
            "i": index,
            "t": round(time.monotonic() - self._start, 3),
            "frame": name,
            "mode": mode,
            "action": decision.action,
            "reason": decision.reason,
            "model_seconds": None if model_seconds is None else round(model_seconds, 3),
            "stuck": stuck,
        }
        if mode == "steer":
            entry["sighting"] = (
                None
                if sighting is None
                else {
                    "visible": sighting.visible,
                    "x": None if sighting.x is None else round(sighting.x, 3),
                    "box": None if sighting.box is None else [round(v, 3) for v in sighting.box],
                }
            )
        with self._log.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
