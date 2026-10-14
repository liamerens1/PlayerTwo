"""CLI entry point: python -m playertwo [--config PATH] [--check]."""

import argparse
import logging
from pathlib import Path

from pydantic import ValidationError

from playertwo.actions import GameProfile
from playertwo.config import Settings

logger = logging.getLogger("playertwo")


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="playertwo")
    parser.add_argument("--config", type=Path, default=Path("config/config.yaml"))
    parser.add_argument(
        "--check", action="store_true", help="validate config and profile, then exit"
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        settings = Settings.load(args.config)
        profile = GameProfile.load(settings.profile)
    except (OSError, ValidationError) as exc:
        print(f"Invalid config or profile:\n{exc}")
        return 1

    logging.basicConfig(level=settings.logging.level, format="%(levelname)s %(name)s: %(message)s")

    print(f"Config OK  model={settings.brain.model}  capture={settings.capture.width}px")
    print(f"Profile OK {profile.name}: {', '.join(profile.action_names)}")
    if args.check:
        return 0

    print("The game loop lands in Phase 3 (feat/game-loop/3). Nothing to run yet.")
    return 0
