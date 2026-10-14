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
5. **`docs/roadmap.md`**: where the project is going. Each phase's goal, its "done" bar
   and its status, plus what's parked and why. The phase table below is its short
   version; keep the two in sync.

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
format) · mypy `--strict` · pytest. Ursina (Panda3D) for the testbed game only.

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

pip install -e ".[dev,testbed]"    # the test game (Ursina)
python -m testbed --level 1        # play it (WASD + mouse); --autopilot to watch, no input
python -m playertwo --profile profiles/testbed.yaml --target-process python.exe --target-window "PlayerTwo Testbed"
python scripts\score_testbed.py --all   # success rate per level, per --tag
```

The testbed (`testbed/`) and PlayerTwo (`src/playertwo/`) never import each other; they
meet only through the screen and input, like a real game (enforced by a test).

## Phases

Short version of [`docs/roadmap.md`](docs/roadmap.md), which has each phase's done bar,
the game ladder and what's parked. Keep the two in sync; reorder only with Liam's OK.

| Phase | Branch                  | Delivers                                                                                   | Status  |
| ----- | ----------------------- | ------------------------------------------------------------------------------------------ | ------- |
| 0     | `feat/scaffold/0`       | Repo, docs, rules, tooling, CI, interfaces, config + profile validation, action executor. | Done    |
| 1     | `feat/capture-input/1`  | dxcam capture, pydirectinput driver, foreground-window guard, F12 kill switch.             | Done    |
| 2     | `feat/brain/2`          | Ollama vision adapter (qwen3-vl:2b-instruct, ~0.56 s/decision): one validated decision per frame. | Done    |
| 3     | `feat/game-loop/3`      | Threaded capture → brain → hands loop, plus the terminal-input safety fix.                 | Done    |
| 4     | `feat/testbed/4`        | Testbed game + Tier 1 short-term memory + Phase 3 review items. Level 1: 20/20 with and without memory; level 2: 1/20. | Done    |
| 5     | `feat/model-upgrades/5` | qwen3-vl:4b-instruct, qwen2.5vl:7b, judged on testbed success per level, decisions/s, VRAM. | Next    |
| 6     | `feat/optimize/6`       | Frame size, change detection, action persistence, judged on testbed numbers.               | Planned |
| 7     | `feat/lessons/7`        | Lessons journal (Tier 2): failure detection → per-game lessons in the prompt. Level 5 (pit) success improves across runs. | Planned |
| 8     | `feat/first-game/8`     | First real game: A Short Hike (fallback SuperTuxKart). Profile + prompt iteration.         | Planned |
| 9     | `feat/recording/9`      | Record frame + human input pairs while Liam plays.                                         | Planned |
| 10    | `feat/imitation/10`     | Imitation learning (Tier 3): LoRA fine-tune a small vision model on the recordings.        | Planned |

Parked: reinforcement learning (Tier 4), game memory reading, online / anti-cheat games.
Reasons in the roadmap.

## Known constraints (don't "fix" these)

- **It will play clumsily.** A model reasoning per frame on an 8 GB card gets roughly 1–5
  decisions per second. Smarter model = slower; faster model = dumber. That tension is
  inherent. Action persistence (each decision is a short behaviour) hides some of it.
- **Exclusive fullscreen may not capture.** Run games in borderless windowed.
- **pydirectinput, not pyautogui.** Many games ignore pyautogui's virtual-key events. Some
  games also need the script run as administrator to accept input. Not a bug.
- **Windows only.** dxcam, pydirectinput and keyboard are Windows libraries, imported
  lazily so pure-logic code and tests still run anywhere.
