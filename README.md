# PlayerTwo

[![CI](https://github.com/liamerens1/PlayerTwo/actions/workflows/ci.yml/badge.svg?branch=dev)](https://github.com/liamerens1/PlayerTwo/actions/workflows/ci.yml)

Let a local AI vision model play your PC games through real keyboard and mouse input.

PlayerTwo captures the screen, hands each frame to a vision model running on your own GPU
(via [Ollama](https://ollama.com)), gets back one action, and performs it. No cloud, no
fees: everything runs on your machine.

> **Status:** Phase 3, game loop. Capture, brain and hands run on their own threads and
> play end to end. Not yet tuned for any real game; the first game profile is Phase 4. See
> [`CLAUDE.md`](CLAUDE.md#phases).

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
- Target the game by its **executable** (find it in Task Manager → Details). You can add
  `--target-window "part of the title"` as an extra check, but don't rely on a title
  alone.
- `--max-seconds 60` stops automatically after a minute.
- To set the target permanently, put it in `safety.target_process` in
  `config/config.yaml`.

When it stops, it prints how many frames went to the model, how many decisions it made
and the median latency, and how many actions it performed or dropped (stale, window not
focused, superseded).

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
replies had to fall back to `wait`.

Read [`CLAUDE.md`](CLAUDE.md), [`docs/coding-guidelines.md`](docs/coding-guidelines.md) and
[`docs/git-workflow.md`](docs/git-workflow.md) before contributing. Work happens on
`feat/<short-description>/<phase>` or `fix/<short-description>` branches, merged into
`dev` by PR.

## Warning

PlayerTwo controls your real keyboard and mouse. Keep F12 within reach. Never use it with
online games or games with anti-cheat.
