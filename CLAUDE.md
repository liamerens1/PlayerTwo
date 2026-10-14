# CLAUDE.md — PlayerTwo

Persistent project rules. These reload every session and override ad-hoc prompts on
conflict.

## Read these first, every session, without exception

1. **`docs/memory/project_memory.md`**: the local, untracked project journal. It records
   every meaningful change, decision, and known issue. Read it **before writing any code
   or answering questions about project state**. It replaces re-deriving context from the
   codebase and keeps the context window small.
2. **`docs/coding-guidelines.md`**: the rules. Check them before writing code, not after
   review catches something.
3. **`docs/architecture.md`**: why the structure is what it is. Read before changing
   structure.
4. **`docs/git-workflow.md`**: branches, commits, PR titles and descriptions.

**Append a dated entry to `project_memory.md` before every commit**, covering: what
changed, why, decisions taken, and any known issue introduced or resolved. Do not skip
this for small changes. The log is the source of truth for history that isn't in the code.

## What this is

PlayerTwo lets a **locally hosted AI vision model play a game on this PC**. It captures
the screen, hands a frame to the model, gets back one action, and performs that action
with real keyboard/mouse input. Personal project, free, Windows only.

The target is real-time third-person games, starting with a simple one with few inputs.
Everything runs locally. A cloud model round-trips every frame over the internet (seconds
per frame), which makes real-time play impossible. That's the whole reason this exists.

**The model is swappable, and the action set is per game. Both are core, not
nice-to-haves.** The bridge code never knows which model is plugged in or which game is
running. Models are a config value; games are profile files. See `docs/architecture.md`.

## Hard rules (non-negotiable)

- **Kill switch first.** Nothing sends input unless the kill switch (default F12) is
  registered. Stopping releases every held key and mouse button. PlayerTwo drives the real
  keyboard and mouse; a runaway loop with W held down is the failure mode to design against.
- **Input only goes to the game window.** Before every action, check the foreground window
  belongs to `safety.target_process` (and matches `safety.target_window` if set). If it
  doesn't, drop the action. Terminals and shells never match: their titles contain the
  command line, so a title-only target matched the terminal and typed into it in Phase 3.
  Alt-tabbing out must make PlayerTwo harmless.
- **Offline single-player only.** Never run against a game with anti-cheat or online play.
  Injected input can get an account flagged or banned.
- **Model output is untrusted input.** Validate every decision with Pydantic against the
  active profile. Unknown action, bad JSON, or out-of-range values become `wait`. Hold
  durations are clamped to the profile's `max_hold_seconds`. Never `eval` model output.
- **Nothing model-specific outside `src/playertwo/brain/`.** No model names, prompts or
  Ollama calls anywhere else. Swapping the model is a one-line config change.
- **Nothing game-specific in code.** Key bindings, action names, goals and limits live in
  `profiles/*.yaml`. A new game is a new profile, not a code change.
- **Local and free.** No cloud APIs, no paid services, no network calls in the loop except
  Ollama on `localhost`.
- **Never block capture on inference.** Capture, brain and hands run on separate threads.
  Always decide on the newest frame; drop stale frames and stale actions, never queue them.
- **No game memory reading** unless a decision to allow it for a specific offline game is
  logged in `project_memory.md` first. Structured state comes from official mod APIs or
  log files by default.

## Git workflow

Full detail in `docs/git-workflow.md`. Summary:

- **Never commit directly to `main` or `dev`.** Work on `feat/<short-description>/<phase>`
  or `fix/<short-description>`, merged via PR into `dev`. `dev` → `main` only at stable
  milestones.
- **PR titles**: `feat: short description` or `fix: short description`.
- **PR descriptions** are full Markdown using `.github/pull_request_template.md`:
  everything that was done, why, and how to verify it.
- **Ask before running `git commit`.**
- **Never add `Co-Authored-By` trailers.**
- Push after each meaningful unit of work, not one blob commit per session.
- Build in phase order; stop at phase boundaries for human review.

## Stack

Python 3.12 · Ollama (local model server) · Pydantic v2 (validation at every boundary) ·
NumPy + Pillow (frames) · dxcam (Desktop Duplication capture) · pydirectinput (DirectInput
scan-code input) · keyboard (kill switch) · PyYAML (config + profiles) · ruff (lint +
format) · mypy `--strict` · pytest.

Hardware it's tuned for: RTX 3070 Ti (**8 GB VRAM**, the real constraint), i7-10700K,
16 GB DDR4 (first pinch point once game + model + OS all compete).

## Commands

```powershell
python -m venv .venv; .venv\Scripts\Activate.ps1
pip install -e ".[dev]"

ruff check .              # lint
ruff format .             # format (ruff format --check . in CI)
mypy                      # strict typecheck
pytest                    # tests

python -m playertwo --check   # validate config + active profile, then exit
python -m playertwo --target-process game.exe   # play; F12 stops, alt-tab pauses
python -m playertwo --target-process notepad.exe --max-seconds 30   # safe live test

ollama pull qwen3-vl:2b-instruct   # starter model (non-thinking)
python scripts\benchmark_brain.py  # decision latency + reply quality, no input sent
```

## Phases

| Phase | Branch                         | Delivers                                                                                       |
| ----- | ------------------------------ | ---------------------------------------------------------------------------------------------- |
| 0     | `feat/scaffold/0`              | Repo, docs, rules, tooling, CI, interfaces, config + profile validation, action executor.     |
| 1     | `feat/capture-input/1`         | Real dxcam capture, pydirectinput driver, foreground-window guard, F12 kill switch.            |
| 2     | `feat/brain/2`                 | Ollama vision adapter (Qwen3-VL 2B): one frame in, one validated decision out. Latency measured. |
| 3     | `feat/game-loop/3`             | Threaded capture → brain → hands loop. Plays a game end to end (badly).                        |
| 4     | `feat/first-game/4`            | First real game profile + prompt iteration. Most play quality lives here.                      |
| 5     | `feat/model-upgrades/5`        | Qwen3-VL 4B instruct, Qwen2.5-VL 7B. Benchmark decisions/sec vs. quality on the 3070 Ti.       |
| 6     | `feat/optimize/6`              | Change-detection tuning, frame size, action persistence, structured state where available.    |
| 7     | `feat/recording/7`             | Record frame + action pairs, for debugging and future fine-tuning of a small specialised model. |

## Known constraints (don't "fix" these)

- **It will play clumsily.** A model reasoning per frame on an 8 GB card gets roughly 1–5
  decisions per second. Smarter model = slower; faster model = dumber. That tension is
  inherent. Action persistence (each decision is a short behaviour) hides some of it.
- **Exclusive fullscreen may not capture.** Run games in borderless windowed.
- **pydirectinput, not pyautogui.** Many games ignore pyautogui's virtual-key events. Some
  games also need the script run as administrator to accept input. Not a bug.
- **Windows only.** dxcam, pydirectinput and keyboard are Windows libraries, imported
  lazily so pure-logic code and tests still run anywhere.
