# PlayerTwo

[![CI](https://github.com/liamerens1/PlayerTwo/actions/workflows/ci.yml/badge.svg?branch=dev)](https://github.com/liamerens1/PlayerTwo/actions/workflows/ci.yml)

Let a local AI vision model play your PC games through real keyboard and mouse input.

PlayerTwo captures the screen, hands each frame to a vision model running on your own GPU
(via [Ollama](https://ollama.com)), gets back one action, and performs it. No cloud, no
fees: everything runs on your machine.

> **Status:** Phases 0–6 done. PlayerTwo plays its own test game with a 2B vision
> model: it **looks** (the model says where the target is) and **steers** (plain code turns
> and walks). That reaches a target that starts off-screen 20/20 times (1/20 when the
> model picked keys itself), gets round walls and obstacles 18–19/20, but still walks into
> pits. The first real game is Phase 9. See the [roadmap](docs/roadmap.md), the single source of
> truth for direction.

## How it works

```
  CAPTURE  --frame-->  BRAIN (swappable model)  --action-->  HANDS (keys / mouse)
     ^                                                            |
     +---------------------- ORCHESTRATOR -------------------------+
```

- **Swappable brain.** The model is one line in `config/config.yaml`. Start with Qwen3-VL 2B
  (fast, crude), step up to Qwen3-VL 4B or Qwen2.5-VL 7B (smarter, slower). Use non-thinking
  ("instruct") models: thinking models spend seconds reasoning before every answer.
- **Per-game profiles.** Each game's actions, key bindings and goal live in
  `profiles/<game>.yaml`. A new game is a new file, not new code.
- **Safe by default.** F12 kills everything and releases held keys. Input is only sent
  while the game window is focused. Model output is validated; anything odd becomes "wait".

Details in [`docs/architecture.md`](docs/architecture.md).

## Requirements

- Windows 10/11
- Python 3.12+
- An NVIDIA GPU (tuned for 8 GB VRAM, e.g. RTX 3070 Ti)
- [Ollama](https://ollama.com/download), kept up to date
- The game in **borderless windowed** mode, offline single-player only

## Setup

PowerShell:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -e ".[dev]"

ollama pull qwen3-vl:2b-instruct

python -m playertwo --check
```

Command Prompt (`cmd.exe`): identical except for activating the venv:

```bat
python -m venv .venv
.venv\Scripts\activate.bat
pip install -e ".[dev]"

ollama pull qwen3-vl:2b-instruct

python -m playertwo --check
```

Every other command in this repo (`ruff`, `mypy`, `pytest`, `git`, `python ...`) is the
same in both shells. Where the docs chain commands with `;` (PowerShell), use `&&` in
Command Prompt.

## Playing

Put the game in **borderless windowed** mode, start Ollama, then:

```bat
python -m playertwo --target-process game.exe
```

- **F12** stops everything and releases every held key.
- Input is only sent while the game's window is focused (after it has been focused for half
  a second); alt-tab out and PlayerTwo is harmless. Terminal windows never receive input.
  While the game isn't focused, capture and the model pause too, so they don't take GPU
  time from whatever you switched to.
- Target the game by its **executable** (find it in Task Manager → Details). You can add
  `--target-window "part of the title"` as an extra check, but don't rely on a title
  alone.
- Only the game window is captured (its inside, without the title bar), on whichever
  monitor it's on. Moving it is fine.
- `--max-seconds 60` stops automatically after a minute. PlayerTwo also stops a few
  seconds after the game window closes.
- `--profile profiles\testbed.yaml` picks a game profile; `--no-memory` turns off
  short-term memory (the model's last few actions in each prompt, and a hint when it
  keeps repeating an action that does nothing).
- If the profile has a `target:` (the testbed's does), PlayerTwo **looks, then steers**:
  the model only says where the target is on screen, and PlayerTwo turns towards it or
  walks at it. `--no-steer` lets the model pick every action itself instead.
- To set the target permanently, put it in `safety.target_process` in
  `config/config.yaml`.

When it stops, it prints how many frames went to the model, how many decisions it made
and the median latency, how many actions it performed or dropped (stale, window not
focused, superseded), how long it was paused and how often the stuck hint was shown.

## The testbed

A tiny third-person game made for PlayerTwo, in `testbed/` (separate from PlayerTwo:
neither imports the other). Walk a blue character to a big yellow cube. Five levels:

1. Open field, cube straight ahead.
2. Cube at a random angle, often off-screen.
3. A wall in the way.
4. Several obstacles.
5. A pit, with unfenced edges: falling is a death.

```bat
pip install -e ".[dev,testbed]"
python -m testbed --level 1
```

W/S walk, A/D strafe, mouse turns, Escape quits. Each episode ends in SUCCESS, YOU FELL or
TIME UP, then a new position (seeded: `--seed`, so runs repeat). It closes after
`--episodes` (default 20) and writes one JSON line per episode to
`testbed\results\<timestamp>.jsonl`. The clock pauses while its window isn't focused.
`--autopilot` lets a built-in path follower play (a demo; it reads the level's layout,
sees nothing and sends no input). `--survey 24 --screenshots DIR` doesn't play at all: it
photographs each start position from 24 headings, for testing what a model can see.

To let PlayerTwo play it, start PlayerTwo first, then the testbed:

```bat
python -m playertwo --profile profiles\testbed.yaml --target-process python.exe --target-window "PlayerTwo Testbed"
python -m testbed --level 1 --tag memory-on
```

The testbed runs as `python.exe`, like PlayerTwo, so give both the process and the window
title. Score the results with:

```bat
python scripts\score_testbed.py --all
```

### Comparing models on the testbed

`scripts\run_testbed_matrix.py` runs every combination of models, levels and memory
on/off, one after another, and writes a comparison table (success rate, median time,
decision time, decisions per minute, peak GPU memory) to
`testbed\results\matrix-<timestamp>.md`:

```bat
ollama pull qwen3-vl:4b-instruct
python scripts\run_testbed_matrix.py --models qwen3-vl:2b-instruct qwen3-vl:4b-instruct --levels 1 2
```

It sends real input to the testbed window, so it waits for Enter before each run; click
the testbed window when it opens and leave the mouse alone. F12 stops PlayerTwo.
`python -m playertwo --model NAME` and `--stats-json PATH` do the same for a single run.

## Development

```powershell
ruff check .
ruff format .
mypy
pytest
```

### Live checks

Some code drives real hardware and can only be verified by hand (it opens Notepad if needed):

```bat
python scripts\verify_phase1.py
```

It captures a frame to `verify_phase1_frame.png`, then checks that input is dropped when
Notepad isn't focused, released when Notepad loses focus, and released by F12. It only
sends input while Notepad is focused.

To measure the model (captures the screen, never sends input; Ollama must be running):

```bat
python scripts\benchmark_brain.py
```

It prints per-decision latency, the median and p90, decisions per second, and how many
replies had to fall back to `wait`. `--target-process` / `--target-window` capture only
a game window (use a moving game: deciding on the same image twice hits Ollama's cache and
looks faster than it is), `--memory` adds a full short-term memory to every prompt to
measure what it costs.

Read [`CLAUDE.md`](CLAUDE.md), [`docs/coding-guidelines.md`](docs/coding-guidelines.md),
[`docs/git-workflow.md`](docs/git-workflow.md) and [`docs/roadmap.md`](docs/roadmap.md)
before contributing. Work happens on
`feat/<short-description>/<phase>` or `fix/<short-description>` branches, merged into
`dev` by PR.

## Warning

PlayerTwo controls your real keyboard and mouse. Keep F12 within reach. Never use it with
online games or games with anti-cheat.
