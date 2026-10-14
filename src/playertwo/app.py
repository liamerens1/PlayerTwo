"""CLI entry point: python -m playertwo [--check] [--target-process EXE] [--profile P] ..."""

import argparse
import logging
import statistics
import threading
import time
from pathlib import Path

from pydantic import ValidationError

from playertwo.actions import GameProfile
from playertwo.brain import BrainUnavailableError, OllamaVisionModel
from playertwo.capture import ChangeDetector, DxcamFrameSource, TargetWindow
from playertwo.config import Settings
from playertwo.hands import ActionExecutor, DirectInputDriver
from playertwo.orchestrator import GameLoop, LoopStats
from playertwo.safety import KillSwitch, SafetyGate, WindowGuard

logger = logging.getLogger("playertwo")

EXIT_OK = 0
EXIT_INVALID_CONFIG = 1
EXIT_NO_TARGET = 2
EXIT_BRAIN_UNAVAILABLE = 3

GAME_WATCH_SECONDS = 1.0
GAME_CLOSED_SECONDS = 3.0
"""Stop this long after the game window disappears."""


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
        "--profile", type=Path, help="game profile to use (overrides profile in the config)"
    )
    parser.add_argument(
        "--no-memory",
        action="store_true",
        help="turn off short-term memory (the model's recent actions in the prompt)",
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
        if args.profile is not None:
            settings = settings.model_copy(update={"profile": args.profile})
        if args.no_memory:
            no_memory = settings.memory.model_copy(update={"enabled": False})
            settings = settings.model_copy(update={"memory": no_memory})
        profile = GameProfile.load(settings.profile)
    except (OSError, ValidationError) as exc:
        print(f"Invalid config or profile:\n{exc}")
        return EXIT_INVALID_CONFIG

    logging.basicConfig(level=settings.logging.level, format="%(levelname)s %(name)s: %(message)s")
    # The ollama client logs every request at INFO through httpx: one line per decision.
    logging.getLogger("httpx").setLevel(max(logging.WARNING, logging.root.level))

    memory = "on" if settings.memory.enabled else "off"
    print(
        f"Config OK  model={settings.brain.model}  capture={settings.capture.width}px  "
        f"memory={memory}"
    )
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
    settings: Settings,
    profile: GameProfile,
    guard: WindowGuard,
    max_seconds: float | None,
) -> int:
    stop = threading.Event()
    model = OllamaVisionModel(settings.brain)
    print(f"Loading {settings.brain.model}...")
    try:
        model.warm_up()
    except BrainUnavailableError as exc:
        print(f"Brain unavailable: {exc}")
        return EXIT_BRAIN_UNAVAILABLE

    # Everything from here on is built inside the try, so a failure while building any of
    # it still releases keys, disarms the kill switch and unloads the model.
    source: DxcamFrameSource | None = None
    kill_switch: KillSwitch | None = None
    executor: ActionExecutor | None = None
    loop: GameLoop | None = None
    timer: threading.Timer | None = None
    exit_code = EXIT_OK
    try:
        target = TargetWindow(guard.matches)
        source = DxcamFrameSource(settings.capture, window=target.rect)
        # The gate needs the kill switch and the kill switch releases the executor's keys;
        # the lambda looks `executor` up when the key fires, by which point it exists.
        kill_switch = KillSwitch(
            settings.safety.kill_switch,
            stop,
            release=lambda: executor.release_all() if executor is not None else None,
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
            memory=settings.memory,
            focused=guard.game_is_focused,
        )

        kill_switch.arm()
        if max_seconds:
            timer = threading.Timer(max_seconds, stop.set)
            timer.daemon = True
            timer.start()
        threading.Thread(
            target=_stop_when_game_closes, args=(target, stop), name="game-watch", daemon=True
        ).start()
        key = settings.safety.kill_switch.upper()
        memory = "on" if settings.memory.enabled else "off"
        print(f"Playing in: {guard.describe()}. Press {key} to stop. Short-term memory {memory}.")
        print("Input is only sent while that window is focused; alt-tab out to pause.")
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
        if executor is not None:
            executor.release_all()
        if kill_switch is not None:
            kill_switch.disarm()
        if source is not None:
            source.close()
        # Otherwise the model sits in VRAM for `keep_alive` after PlayerTwo exits, which
        # the game may need.
        model.unload()
    if loop is not None:
        print(_summary(loop.stats))
    return exit_code


def _stop_when_game_closes(target: TargetWindow, stop: threading.Event) -> None:
    """Stop once the game window has been seen and then stays gone, e.g. the game quit."""
    gone_since: float | None = None
    while not stop.wait(GAME_WATCH_SECONDS):
        if target.handle() is not None:
            gone_since = None
        elif target.ever_found:
            gone_since = gone_since or time.monotonic()
            if time.monotonic() - gone_since >= GAME_CLOSED_SECONDS:
                print("The game window closed; stopping.")
                stop.set()


def _summary(stats: LoopStats) -> str:
    latency = (
        f"median {statistics.median(stats.decide_seconds):.2f} s" if stats.decide_seconds else "n/a"
    )
    return (
        f"Stopped. frames sent to the model {stats.frames_published} "
        f"(skipped {stats.frames_skipped}), decisions {stats.decisions} ({latency}), "
        f"performed {stats.actions_performed}, dropped: stale {stats.dropped_stale}, "
        f"window not focused {stats.dropped_by_gate}, superseded {stats.decisions_skipped}; "
        f"paused {stats.paused_seconds:.0f} s, stuck hints {stats.stuck_hints}"
    )
