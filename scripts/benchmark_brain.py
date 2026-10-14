"""Measure how fast and how sane the configured model's decisions are. Phase 2.

Run from the repo root with Ollama running:

    python scripts\\benchmark_brain.py                 # 20 decisions on live screen captures
    python scripts\\benchmark_brain.py --frames 50
    python scripts\\benchmark_brain.py --image verify_phase1_frame.png

Uses brain.model and the active profile from config/config.yaml. Captures the screen
but never sends keyboard or mouse input: nothing here touches `hands`.
"""

import argparse
import statistics
import sys
import time
from collections import Counter
from pathlib import Path

import numpy as np
from PIL import Image

from playertwo.actions import GameProfile
from playertwo.brain import BrainUnavailableError, OllamaVisionModel
from playertwo.capture import DxcamFrameSource, downscale_to_width
from playertwo.config import Settings
from playertwo.types import Frame

ROOT = Path(__file__).resolve().parents[1]
FALLBACK_REASONS = ("unparseable reply", "ollama error", "no reply within", "unknown action")
"""Reasons the adapter gives when it substitutes `wait` for a bad reply or failed call."""


def _percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, round(fraction * (len(ordered) - 1)))]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--frames", type=int, default=20, help="number of decisions")
    parser.add_argument("--image", type=Path, help="use this image instead of live capture")
    args = parser.parse_args()

    settings = Settings.load(ROOT / "config" / "config.yaml")
    profile = GameProfile.load(ROOT / settings.profile)
    model = OllamaVisionModel(settings.brain)
    print(f"model {settings.brain.model}  profile {profile.name}  frames {args.frames}")

    source: DxcamFrameSource | None = None
    still: Frame | None = None
    if args.image:
        rgb: Frame = np.asarray(Image.open(args.image).convert("RGB"), dtype=np.uint8)
        still = downscale_to_width(rgb, settings.capture.width)
    else:
        source = DxcamFrameSource(settings.capture)

    try:
        start = time.monotonic()
        model.warm_up()
        print(f"warm-up (model load): {time.monotonic() - start:.2f} s\n")

        totals: list[float] = []
        actions: Counter[str] = Counter()
        fallbacks = 0
        frame = still
        for i in range(args.frames):
            if source is not None:
                # None means the screen hasn't changed; decide on the last frame again.
                grabbed = source.grab()
                if grabbed is not None:
                    frame = grabbed
                deadline = time.monotonic() + 2.0
                while frame is None and time.monotonic() < deadline:
                    time.sleep(0.02)
                    frame = source.grab()
            if frame is None:
                print("no frame captured within 2 s")
                return 1
            decision = model.decide(frame, profile)
            stats = model.last_stats
            assert stats is not None
            totals.append(stats.total_seconds)
            actions[decision.action] += 1
            reason = decision.reason or ""
            fallbacks += decision.action == "wait" and reason.startswith(FALLBACK_REASONS)
            print(
                f"{i + 1:3d}  {stats.total_seconds:5.2f} s  "
                f"(image+prompt {stats.prompt_tokens} tok {stats.prompt_seconds:.2f} s, "
                f"reply {stats.reply_tokens} tok {stats.reply_seconds:.2f} s)  "
                f"{decision.action:<14} {decision.reason or ''}"
            )
    except BrainUnavailableError as exc:
        print(f"\nBrain unavailable: {exc}")
        return 1
    finally:
        if source is not None:
            source.close()

    median = statistics.median(totals)
    print(
        f"\nlatency  min {min(totals):.2f}  median {median:.2f}  "
        f"p90 {_percentile(totals, 0.9):.2f}  max {max(totals):.2f} s"
    )
    print(f"throughput  about {1 / median:.1f} decisions/s (at the median)")
    print(f"actions  {dict(actions)}")
    print(f"fallbacks to wait (bad reply / error)  {fallbacks}/{len(totals)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
