"""CLI entry point: python -m playertwo [--check] [--target-process EXE] [--target-window TITLE]."""

import argparse
import logging
import statistics
import threading
from pathlib import Path

from pydantic import ValidationError

from playertwo.actions import GameProfile
from playertwo.brain import BrainUnavailableError, OllamaVisionModel
from playertwo.capture import ChangeDetector, DxcamFrameSource
from playertwo.config import Settings
from playertwo.hands import ActionExecutor, DirectInputDriver
from playertwo.orchestrator import GameLoop, LoopStats
from playertwo.safety import KillSwitch, SafetyGate, WindowGuard

logger = logging.getLogger("playertwo")

EXIT_OK = 0
EXIT_INVALID_CONFIG = 1
EXIT_NO_TARGET = 2
EXIT_BRAIN_UNAVAILABLE = 3


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="playertwo")
    parser.add_argument("--config", type=Path, default=Path("config/config.yaml"))
    parser.add_argument(
        "--check", action="store_true", help="validate config and profile, then exit"
    )
    parser.add_argument(
        "--target-process",
        help="the game's executable, e.g. game.exe (overrides safety.target_process)",
    )
    parser.add_argument(
        "--target-window",
        help="substring of the game's window title (overrides safety.target_window)",
    )
    parser.add_argument(
        "--max-seconds",
        type=float,
        help="stop automatically after this many seconds (in addition to the kill switch)",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        settings = Settings.load(args.config)
        profile = GameProfile.load(settings.profile)
    except (OSError, ValidationError) as exc:
        print(f"Invalid config or profile:\n{exc}")
        return EXIT_INVALID_CONFIG

    logging.basicConfig(level=settings.logging.level, format="%(levelname)s %(name)s: %(message)s")
    # The ollama client logs every request at INFO through httpx: one line per decision.
    logging.getLogger("httpx").setLevel(max(logging.WARNING, logging.root.level))

    print(f"Config OK  model={settings.brain.model}  capture={settings.capture.width}px")
    print(f"Profile OK {profile.name}: {', '.join(profile.action_names)}")
    if args.check:
        return EXIT_OK

    guard = WindowGuard(
        target_window=args.target_window or settings.safety.target_window,
        target_process=args.target_process or settings.safety.target_process,
    )
    if not guard.describe():
        print(
            "No target. Set safety.target_process (recommended) or safety.target_window "
            "in config/config.yaml, or pass --target-process / --target-window. "
            "PlayerTwo only sends input to that window."
        )
        return EXIT_NO_TARGET
    return _play(settings, profile, guard, args.max_seconds)


def _play(
    settings: Settings, profile: GameProfile, guard: WindowGuard, max_seconds: float | None
) -> int:
    stop = threading.Event()
    model = OllamaVisionModel(settings.brain)
    print(f"Loading {settings.brain.model}...")
    try:
        model.warm_up()
    except BrainUnavailableError as exc:
        print(f"Brain unavailable: {exc}")
        return EXIT_BRAIN_UNAVAILABLE

    source = DxcamFrameSource(settings.capture)
    # The gate needs the kill switch and the kill switch releases the executor's keys;
    # the lambda looks `executor` up when the key fires, by which point it exists.
    kill_switch = KillSwitch(
        settings.safety.kill_switch, stop, release=lambda: executor.release_all()
    )
    gate = SafetyGate(kill_switch, guard, settle_seconds=settings.safety.focus_settle_seconds)
    executor = ActionExecutor(DirectInputDriver(), profile, stop, gate)
    loop = GameLoop(
        source,
        ChangeDetector(settings.capture.change_threshold),
        model,
        executor,
        profile,
        stop,
        settings.loop,
        fps=settings.capture.fps,
        republish_seconds=settings.capture.republish_seconds,
    )

    kill_switch.arm()
    timer = threading.Timer(max_seconds, stop.set) if max_seconds else None
    key = settings.safety.kill_switch.upper()
    print(f"Playing in: {guard.describe()}. Press {key} to stop.")
    print("Input is only sent while that window is focused; alt-tab out to pause.")
    exit_code = EXIT_OK
    try:
        if timer is not None:
            timer.daemon = True
            timer.start()
        loop.run()
    except BrainUnavailableError as exc:
        print(f"Brain unavailable: {exc}")
        exit_code = EXIT_BRAIN_UNAVAILABLE
    except KeyboardInterrupt:
        print("Interrupted.")
    finally:
        stop.set()
        if timer is not None:
            timer.cancel()
        executor.release_all()
        kill_switch.disarm()
        source.close()
        # Otherwise the model sits in VRAM for `keep_alive` after PlayerTwo exits, which
        # the game may need.
        model.unload()
    print(_summary(loop.stats))
    return exit_code


def _summary(stats: LoopStats) -> str:
    latency = (
        f"median {statistics.median(stats.decide_seconds):.2f} s" if stats.decide_seconds else "n/a"
    )
    return (
        f"Stopped. frames sent to the model {stats.frames_published} "
        f"(skipped {stats.frames_skipped}), decisions {stats.decisions} ({latency}), "
        f"performed {stats.actions_performed}, dropped: stale {stats.dropped_stale}, "
        f"window not focused {stats.dropped_by_gate}, superseded {stats.decisions_skipped}"
    )
