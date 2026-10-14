"""python -m testbed --level N [--seed S] [--episodes K] ..."""

import argparse
import logging
from pathlib import Path

from testbed.levels import LEVELS
from testbed.results import RESULTS_DIR, new_results_path


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    levels = "\n".join(f"  {n}: {info.name}" for n, info in LEVELS.items())
    parser = argparse.ArgumentParser(
        prog="python -m testbed",
        description=f"PlayerTwo's test game. Reach the yellow cube.\n\nLevels:\n{levels}",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--level", type=int, choices=sorted(LEVELS), default=1)
    parser.add_argument(
        "--seed", type=int, default=1, help="episode k uses seed S + k - 1 (default 1)"
    )
    parser.add_argument(
        "--episodes", type=int, default=20, help="close after this many episodes (default 20)"
    )
    parser.add_argument(
        "--timeout", type=float, help="seconds per episode (default: the level's own)"
    )
    parser.add_argument("--tag", default="", help="label stored with every result, e.g. memory-on")
    parser.add_argument(
        "--results-dir", type=Path, default=RESULTS_DIR, help="where the .jsonl file goes"
    )
    parser.add_argument(
        "--autopilot",
        action="store_true",
        help="let a built-in path follower play (demo; sends no real input)",
    )
    parser.add_argument(
        "--screenshots", type=Path, help="save one screenshot per episode into this folder"
    )
    parser.add_argument(
        "--verbose", action="store_true", help="log every mouse turn (to check sensitivity)"
    )
    args = parser.parse_args(argv)
    if args.episodes < 1:
        parser.error("--episodes must be at least 1")
    if args.timeout is not None and args.timeout <= 0:
        parser.error("--timeout must be positive")
    return args


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(level=level, format="%(levelname)s %(name)s: %(message)s")
    from testbed.game import GameOptions, run_game  # imports Ursina

    results_path = new_results_path(args.results_dir)
    print(f"Level {args.level}: {LEVELS[args.level].name}. Results: {results_path}")
    run_game(
        GameOptions(
            level=args.level,
            seed=args.seed,
            episodes=args.episodes,
            timeout_seconds=args.timeout,
            results_path=results_path,
            tag=args.tag,
            autopilot=args.autopilot,
            screenshot_dir=args.screenshots,
        )
    )
    return 0
