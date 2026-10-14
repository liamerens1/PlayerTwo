"""Summarise testbed results: success rate, median time, deaths and timeouts per level.

Run from the repo root:

    python scripts\\score_testbed.py                          # the newest results file
    python scripts\\score_testbed.py testbed\\results\\a.jsonl testbed\\results\\b.jsonl
    python scripts\\score_testbed.py --all                    # every file in testbed\\results

Rows are grouped by the run's --tag (e.g. memory-on / memory-off) and level, so two runs
can be compared side by side. Doesn't need Ursina.
"""

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))  # the testbed package lives at the repo root, not in src/

from testbed.results import RESULTS_DIR, format_summary, load_results, summarise  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("files", nargs="*", type=Path, help="results files (.jsonl)")
    parser.add_argument("--all", action="store_true", help=f"every file in {RESULTS_DIR}")
    args = parser.parse_args()

    files: list[Path] = args.files
    if args.all or not files:
        found = sorted(RESULTS_DIR.glob("*.jsonl"))
        if not found:
            print(f"No results in {RESULTS_DIR}. Play with: python -m testbed --level 1")
            return 1
        files = found if args.all else found[-1:]

    results = []
    for path in files:
        loaded = load_results(path)
        print(f"{path}: {len(loaded)} episodes")
        results.extend(loaded)
    print()
    print(format_summary(summarise(results)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
