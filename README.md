# PlayerTwo

Let a local AI vision model play your PC games through real keyboard and mouse input.

PlayerTwo captures the screen, hands each frame to a vision model running on your own GPU
(via [Ollama](https://ollama.com)), gets back one action, and performs it. No cloud, no
fees: everything runs on your machine.

> **Status:** Phase 0, scaffold. The structure, rules, config and safety-critical executor
> are in place; capture, the model adapter and the loop land in Phases 1–3. See
> [`CLAUDE.md`](CLAUDE.md#phases).

## How it works

```
  CAPTURE  --frame-->  BRAIN (swappable model)  --action-->  HANDS (keys / mouse)
     ^                                                            |
     +---------------------- ORCHESTRATOR -------------------------+
```

- **Swappable brain.** The model is one line in `config/config.yaml`. Start with Moondream
  (fast, crude), step up to Qwen3-VL 4B or Qwen2.5-VL 7B (smarter, slower).
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

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -e ".[dev]"

ollama pull moondream

python -m playertwo --check
```

## Development

```powershell
ruff check .
ruff format .
mypy
pytest
```

Read [`CLAUDE.md`](CLAUDE.md), [`docs/coding-guidelines.md`](docs/coding-guidelines.md) and
[`docs/git-workflow.md`](docs/git-workflow.md) before contributing. Work happens on
`feat/<short-description>/<phase>` or `fix/<short-description>` branches, merged into
`dev` by PR.

## Warning

PlayerTwo controls your real keyboard and mouse. Keep F12 within reach. Never use it with
online games or games with anti-cheat.
