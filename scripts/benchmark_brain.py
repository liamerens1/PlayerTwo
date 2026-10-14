"""Measure how fast and how sane the configured model's decisions are. Phase 2.

Run from the repo root with Ollama running:

    python scripts\\benchmark_brain.py                 # 20 decisions on live screen captures
    python scripts\\benchmark_brain.py --frames 50
    python scripts\\benchmark_brain.py --image verify_phase1_frame.png
    python scripts\\benchmark_brain.py --memory       # with a full short-term memory in the prompt
    python scripts\\benchmark_brain.py --profile profiles\\testbed.yaml ^
        --target-process python.exe --target-window "PlayerTwo Testbed"

Use live captures for latency: deciding on one --image over and over lets Ollama reuse
its cache of the image and looks much faster than real play.

Uses brain.model and the active profile from config/config.yaml. Captures the screen
but never sends keyboard or mouse input: nothing here touches `hands`.
"""

import argparse
import io
import statistics
import sys
import time
from collections import Counter
from pathlib import Path

import numpy as np
from PIL import Image

from playertwo.actions import GameProfile, History, PastAction
from playertwo.brain import BrainUnavailableError, OllamaVisionModel
from playertwo.capture import DxcamFrameSource, TargetWindow, downscale_to_width
from playertwo.config import Settings
from playertwo.safety import WindowGuard
from playertwo.types import Frame

ROOT = Path(__file__).resolve().parents[1]
FALLBACK_REASONS = (
    "unparseable reply",
    "ollama error",
    "no reply within",
    "connection error",
    "unknown action",
)
"""Reasons the adapter gives when it substitutes `wait` for a bad reply or failed call."""


def _percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, round(fraction * (len(ordered) - 1)))]


def _full_history(profile: GameProfile, size: int) -> History:
    """A memory as long as it gets: `size` actions with long reasons, plus the stuck hint."""
    action = next(name for name in profile.action_names if name != "wait")
    past = PastAction(action, "the target is ahead, keep going that way", False)
    return History((past,) * size, stuck_action=action, stuck_repeats=size)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--frames", type=int, default=20, help="number of decisions")
    parser.add_argument("--image", type=Path, help="use this image instead of live capture")
    parser.add_argument("--profile", type=Path, help="profile to use instead of the config's")
    parser.add_argument(
        "--target-process", help="capture only this program's window, e.g. game.exe"
    )
    parser.add_argument("--target-window", help="capture only the window with this in its title")
    parser.add_argument(
        "--memory",
        action="store_true",
        help="send a full short-term memory with every decision (the longest prompt it makes)",
    )
    args = parser.parse_args()
    # Models sometimes write characters the Windows console code page can't encode (seen
    # when output was redirected to a file); print them escaped instead of crashing.
    if isinstance(sys.stdout, io.TextIOWrapper):
        sys.stdout.reconfigure(errors="backslashreplace")

    settings = Settings.load(ROOT / "config" / "config.yaml")
    profile = GameProfile.load(args.profile or ROOT / settings.profile)
    history = _full_history(profile, settings.memory.size) if args.memory else None
    model = OllamaVisionModel(settings.brain)
    memory = "full" if history is not None else "off"
    print(
        f"model {settings.brain.model}  profile {profile.name}  frames {args.frames}  "
        f"memory {memory}"
    )

    source: DxcamFrameSource | None = None
    still: Frame | None = None
    if args.image:
        rgb: Frame = np.asarray(Image.open(args.image).convert("RGB"), dtype=np.uint8)
        still = downscale_to_width(rgb, settings.capture.width)
    elif args.target_process or args.target_window:
        guard = WindowGuard(args.target_window or "", args.target_process or "")
        source = DxcamFrameSource(settings.capture, window=TargetWindow(guard.matches).rect)
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
            decision = model.decide(frame, profile, history)
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
