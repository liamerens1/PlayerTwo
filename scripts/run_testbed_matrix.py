"""Run PlayerTwo on the testbed for several models, levels and memory settings. Phase 5.

Run from the repo root with Ollama running and the models pulled:

    python scripts\\run_testbed_matrix.py --models qwen3-vl:2b-instruct qwen3-vl:4b-instruct
    python scripts\\run_testbed_matrix.py --models qwen2.5vl:7b --levels 2 --memory off

SENDS REAL KEYBOARD AND MOUSE INPUT, through PlayerTwo and only to the testbed window
(F12 stops PlayerTwo; alt-tab pauses both). For each run it:

1. waits for Enter (skip with --no-pause), so nothing starts without you;
2. starts PlayerTwo with --model, --no-memory if asked, and --stats-json;
3. opens the testbed once PlayerTwo is ready. Click its window to start, then leave the
   mouse alone: the mouse turns the character;
4. waits for the episodes, then for PlayerTwo to stop by itself (it does a few seconds
   after the testbed closes);
5. samples GPU memory with nvidia-smi from before PlayerTwo starts until it stops.

Writes testbed\\results\\matrix-<timestamp>.md (a table per run: success rate, median
time, decision latency, decisions per minute, peak GPU memory) and keeps every log, run
summary and results file in testbed\\results\\matrix-<timestamp>\\.
"""

import argparse
import json
import statistics
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))  # the testbed package lives at the repo root, not in src/

from testbed.episode import EpisodeResult, Outcome  # noqa: E402
from testbed.results import RESULTS_DIR, load_results  # noqa: E402

PROFILE = "profiles/testbed.yaml"
TARGET = ["--target-process", "python.exe", "--target-window", "PlayerTwo Testbed"]
OLLAMA_TAGS = "http://127.0.0.1:11434/api/tags"
READY_TIMEOUT_SECONDS = 300.0
"""A cold 7B model can take minutes to load the first time."""
STOP_GRACE_SECONDS = 30.0
GPU_SAMPLE_SECONDS = 1.0


@dataclass(frozen=True)
class Combo:
    model: str
    level: int
    memory: bool

    @property
    def tag(self) -> str:
        return f"{self.model} L{self.level} mem-{'on' if self.memory else 'off'}"

    @property
    def slug(self) -> str:
        """For file names: no ':' or '/'."""
        safe = self.model.replace(":", "_").replace("/", "_")
        return f"{safe}-l{self.level}-mem-{'on' if self.memory else 'off'}"


def plan(models: list[str], levels: list[int], memory: str) -> list[Combo]:
    """Every combination, grouped by model so each model loads once per memory setting."""
    settings = {"on": [True], "off": [False], "both": [True, False]}[memory]
    return [Combo(m, lvl, mem) for m in models for lvl in levels for mem in settings]


@dataclass(frozen=True)
class RunOutcome:
    combo: Combo
    results: list[EpisodeResult]
    report: dict[str, object] | None
    """PlayerTwo's --stats-json, or None if it didn't write one."""
    gpu_baseline_mib: int | None
    gpu_peak_mib: int | None


def format_matrix(outcomes: list[RunOutcome]) -> str:
    """A Markdown table, one row per run."""
    rows = [
        "| Model | Level | Memory | Success | Median time | Time-outs | Fell "
        "| Decision (median) | Decisions/min | Peak GPU MiB | Model+game MiB |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for o in outcomes:
        wins = [r.seconds for r in o.results if r.outcome is Outcome.SUCCESS]
        n = len(o.results)
        median_time = f"{statistics.median(wins):.1f} s" if wins else "-"
        timeouts = sum(r.outcome is Outcome.TIMEOUT for r in o.results)
        fell = sum(r.outcome is Outcome.FELL for r in o.results)
        report = o.report or {}
        decide = report.get("decide_median_seconds")
        per_minute = report.get("decisions_per_minute")
        delta = (
            o.gpu_peak_mib - o.gpu_baseline_mib
            if o.gpu_peak_mib is not None and o.gpu_baseline_mib is not None
            else None
        )
        rows.append(
            f"| {o.combo.model} | {o.combo.level} | {'on' if o.combo.memory else 'off'} "
            f"| {len(wins)}/{n} | {median_time} | {timeouts} | {fell} "
            f"| {f'{decide:.2f} s' if isinstance(decide, float) else '-'} "
            f"| {per_minute if per_minute is not None else '-'} "
            f"| {o.gpu_peak_mib if o.gpu_peak_mib is not None else '-'} "
            f"| {delta if delta is not None else '-'} |"
        )
    return "\n".join(rows)


def installed_models() -> set[str] | None:
    """Model names Ollama has pulled, or None if Ollama isn't reachable."""
    try:
        with urllib.request.urlopen(OLLAMA_TAGS, timeout=5) as response:
            data = json.load(response)
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
        return None
    return {entry["name"] for entry in data.get("models", [])}


class GpuSampler:
    """Polls nvidia-smi for used GPU memory; remembers the peak. Quietly does nothing if
    nvidia-smi isn't available."""

    def __init__(self) -> None:
        self.peak: int | None = None
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, name="gpu-sampler", daemon=True)

    @staticmethod
    def sample() -> int | None:
        try:
            out = subprocess.run(
                ["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
                capture_output=True,
                text=True,
                timeout=5,
                check=True,
            ).stdout
        except (OSError, subprocess.SubprocessError):
            return None
        first = out.strip().splitlines()[0] if out.strip() else ""
        return int(first) if first.isdigit() else None

    def _run(self) -> None:
        while not self._stop.wait(GPU_SAMPLE_SECONDS):
            used = self.sample()
            if used is not None:
                self.peak = used if self.peak is None else max(self.peak, used)

    def __enter__(self) -> "GpuSampler":
        self._thread.start()
        return self

    def __exit__(self, *_: object) -> None:
        self._stop.set()
        self._thread.join(timeout=10)


def _wait_for_line(
    log: Path, needle: str, process: subprocess.Popen[bytes], timeout: float
) -> bool:
    """True once `needle` appears in the log; False if the process exits or time runs out."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if log.exists() and needle in log.read_text(encoding="utf-8", errors="replace"):
            return True
        if process.poll() is not None:
            return False
        time.sleep(0.5)
    return False


def run_one(combo: Combo, args: argparse.Namespace, out_dir: Path) -> RunOutcome | None:
    """One PlayerTwo + testbed run. None if PlayerTwo failed to start."""
    p2_log = out_dir / f"{combo.slug}-playertwo.log"
    tb_log = out_dir / f"{combo.slug}-testbed.log"
    stats = out_dir / f"{combo.slug}-stats.json"
    results_dir = out_dir / combo.slug
    p2_cmd = [sys.executable, "-u", "-m", "playertwo", "--profile", PROFILE, *TARGET]
    p2_cmd += ["--model", combo.model, "--stats-json", str(stats)]
    if not combo.memory:
        p2_cmd.append("--no-memory")
    tb_cmd = [sys.executable, "-u", "-m", "testbed", "--level", str(combo.level)]
    tb_cmd += ["--episodes", str(args.episodes), "--seed", str(args.seed), "--tag", combo.tag]
    tb_cmd += ["--results-dir", str(results_dir)]

    baseline = GpuSampler.sample()
    with GpuSampler() as gpu, p2_log.open("wb") as p2_out:
        playertwo = subprocess.Popen(p2_cmd, cwd=ROOT, stdout=p2_out, stderr=subprocess.STDOUT)
        print(f"  loading {combo.model}...")
        if not _wait_for_line(p2_log, "Playing in", playertwo, READY_TIMEOUT_SECONDS):
            print(f"  PlayerTwo didn't start; see {p2_log}")
            if playertwo.poll() is None:
                print("  It's still running: press F12 to stop it.")
                playertwo.wait()
            return None
        print("  ready. Click the PlayerTwo Testbed window to start, then hands off the mouse.")
        with tb_log.open("wb") as tb_out:
            subprocess.run(tb_cmd, cwd=ROOT, stdout=tb_out, stderr=subprocess.STDOUT, check=False)
        try:
            playertwo.wait(timeout=STOP_GRACE_SECONDS)
        except subprocess.TimeoutExpired:
            # Never kill it: a killed PlayerTwo can't release a held key.
            print("  PlayerTwo is still running after the testbed closed. Press F12.")
            playertwo.wait()

    results = [r for f in sorted(results_dir.glob("*.jsonl")) for r in load_results(f)]
    report = json.loads(stats.read_text(encoding="utf-8")) if stats.exists() else None
    return RunOutcome(combo, results, report, baseline, gpu.peak)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--models", nargs="+", required=True, help="Ollama model names")
    parser.add_argument("--levels", nargs="+", type=int, default=[1, 2])
    parser.add_argument("--memory", choices=["on", "off", "both"], default="both")
    parser.add_argument("--episodes", type=int, default=20)
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument(
        "--no-pause", action="store_true", help="don't wait for Enter before each run"
    )
    args = parser.parse_args()

    installed = installed_models()
    if installed is None:
        print("Ollama isn't reachable on 127.0.0.1:11434. Start it first.")
        return 1
    missing = [m for m in args.models if m not in installed]
    if missing:
        print("Not pulled yet:\n" + "\n".join(f"  ollama pull {m}" for m in missing))
        return 1

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    out_dir = RESULTS_DIR / f"matrix-{stamp}"
    out_dir.mkdir(parents=True, exist_ok=True)
    combos = plan(args.models, args.levels, args.memory)
    print(f"{len(combos)} runs of {args.episodes} episodes. Output: {out_dir}")
    print("This sends real keyboard and mouse input to the testbed window. F12 stops PlayerTwo.")

    outcomes: list[RunOutcome] = []
    try:
        for i, combo in enumerate(combos, 1):
            print(f"\n[{i}/{len(combos)}] {combo.tag}")
            if not args.no_pause:
                input("  Press Enter to start (Ctrl+C to stop here)... ")
            outcome = run_one(combo, args, out_dir)
            if outcome is None:
                return 1
            outcomes.append(outcome)
            print(format_matrix([outcome]).splitlines()[-1])
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        if outcomes:
            table = format_matrix(outcomes)
            summary = RESULTS_DIR / f"matrix-{stamp}.md"
            summary.write_text(
                f"# Testbed matrix {stamp}\n\nSeed {args.seed}, {args.episodes} episodes "
                f"per run.\n\n{table}\n",
                encoding="utf-8",
            )
            print(f"\n{table}\n\nWritten to {summary}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
