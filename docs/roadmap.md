# Roadmap — PlayerTwo

Where PlayerTwo is going, phase by phase. `CLAUDE.md`'s phase table is the short version
of this document; **the two must always match** (same numbers, names and branches).
Change the order only with Liam's OK, and record the change in
`docs/memory/project_memory.md`.

Each phase has a goal, a **done bar** (measurable where possible) and a status. Bars
marked _(proposed)_ haven't been agreed yet; confirm them before the phase starts.

**Memory and learning tiers.** These come up in several phases:

| Tier | What                                                                   | Phase    |
| ---- | ---------------------------------------------------------------------- | -------- |
| 1    | Short-term memory: recent decisions carried into the next prompt.      | 4        |
| 2    | Lessons journal: one-line lessons per game, learned from failures.     | 7        |
| 3    | Imitation learning: fine-tune a small vision model on recorded play.   | 10       |
| 4    | Reinforcement learning.                                                | Parked   |

---

## Done

### 0. Scaffold — `feat/scaffold/0`

- **Goal:** repo, rules, docs, tooling, interfaces, config and profile validation, and the
  safety-critical action executor.
- **Done bar:** ruff, mypy strict and pytest pass; `python -m playertwo --check` validates
  config and profile. CI was added afterwards (`fix/ci-and-pr-template`) and passes on
  Python 3.12.
- **Status:** ✅ done (PR #1).

### 1. Capture + input + safety — `feat/capture-input/1`

- **Goal:** real dxcam capture, pydirectinput input, foreground-window guard, F12 kill
  switch.
- **Done bar:** `scripts/verify_phase1.py` passes 4/4 live against Notepad: frame
  captured, input dropped when unfocused, a held key released on focus loss, a held key
  released by **one** F12 press.
- **Status:** ✅ done (PR #2). Found and fixed: `keyboard.add_hotkey` ignored F12 while
  another key was held.

### 2. Brain — `feat/brain/2`

- **Goal:** one frame in, one validated decision out, through Ollama; latency measured.
- **Done bar:** `scripts/benchmark_brain.py` on live captures: every reply valid (0/20
  fallbacks to `wait`), latency measured.
- **Status:** ✅ done (PR #4). `qwen3-vl:2b-instruct`, **about 0.56 s per decision**
  (about 1.7 decisions/s) on the RTX 3070 Ti. Moondream dropped (broken on Ollama 0.40).

### 3. Game loop — `feat/game-loop/3`

- **Goal:** capture, brain and hands on separate threads with single-slot hand-offs;
  plays end to end.
- **Done bar:** live run against Notepad where actions performed = characters in
  Notepad, **zero input reaches any other window** while alt-tabbed, and one F12 press
  stops everything and unloads the model.
- **Status:** ✅ done (PR #5). Includes the **terminal-input safety fix**: a title-only
  target matched the terminal running PlayerTwo and typed into it; the guard now matches
  the game's executable (`--target-process`) and never a terminal.

---

## Next

### 4. Testbed game + Tier 1 short-term memory + Phase 3 review items — `feat/testbed/4`

- **Goal:**
  - **Testbed game:** a small game with numbered levels that PlayerTwo plays like any
    other game, but which reports success or failure so play can be scored. Level 1 is
    the baseline; level 5 has a pit (the failure case Phase 7 learns from).
  - **Tier 1 short-term memory:** recent decisions carried into the prompt.
  - **Phase 3 review items.** Candidates from PR #5's known issues, to be replaced by
    the planning review's list when it arrives:
    - every decision is `move_forward` on non-game screens;
    - on a static screen decisions come only every 2 s (`republish_seconds`,
      `change_threshold`);
    - about 1 in 10 decisions is dropped as stale while a hold is running;
    - `TERMINAL_PROCESSES` is a fixed list (e.g. VS Code's terminal isn't in it).
- **Done bar:** **level 1 success rate measured, with and without Tier 1 memory**, over
  the same number of attempts (≥ 20 _(proposed)_).
- **Status:** ⏭ next.

### 5. Model upgrades — `feat/model-upgrades/5`

- **Goal:** try `qwen3-vl:4b-instruct` and `qwen2.5vl:7b` against the 2B baseline.
- **Done bar:** for each model, testbed **success rate per level**, **decisions/s**, and
  **VRAM used while a game is running**, recorded side by side, and a default model
  chosen from them.
- **Status:** planned.

### 6. Optimise — `feat/optimize/6`

- **Goal:** frame size, change detection, action persistence.
- **Done bar:** every change is judged on testbed numbers. One is kept only if it improves
  success rate or decisions/s without making the other worse _(proposed)_.
- **Status:** planned. Known lever: image tokens are about 70% of decision time
  (0.38 of 0.56 s at 640 px).

### 7. Lessons journal (Tier 2) — `feat/lessons/7`

- **Goal:** detect deaths and failures, write one-line lessons per game, and feed them
  into the prompt. Testbed deaths are the first signal.
- **Done bar:** **level 5 (pit) success rate improves across runs** as lessons
  accumulate.
- **Status:** planned.

### 8. First real game — `feat/first-game/8`

- **Goal:** a profile and prompt iteration for **A Short Hike** (fallback:
  **SuperTuxKart**). Offline, single-player, no anti-cheat.
- **Done bar** _(proposed)_: reaches a defined in-game goal in a measured share of
  attempts. The goal and target rate are agreed when the phase starts.
- **Status:** planned.

### 9. Recording — `feat/recording/9`

- **Goal:** record frame + human input pairs while Liam plays.
- **Done bar** _(proposed)_: a documented dataset format; frames and inputs time-aligned
  and replayable; enough hours recorded for Phase 10 (amount agreed then).
- **Status:** planned.

### 10. Imitation learning (Tier 3) — `feat/imitation/10`

- **Goal:** LoRA fine-tune a small vision model on the Phase 9 recordings.
- **Done bar** _(proposed)_: the fine-tuned model beats the prompt-only model's testbed
  success rate at equal or better decisions/s.
- **Status:** planned.

---

## Game ladder (after Phase 10)

From light to heavy, as VRAM allows next to the model:

1. LEGO Lord of the Rings / LEGO Pirates of the Caribbean
2. Tomb Raider (2013)
3. The Walking Dead
4. Heavier titles: The Witcher 3, Spider-Man, Red Dead Redemption 2

Every game must be playable offline and single-player with no anti-cheat.

---

## Parked

- **Reinforcement learning (Tier 4).** Needs millions of attempts, and commercial games
  can't be sped up or run in parallel. Revisit only for the testbed, which could run
  headless and fast.
- **Game memory reading.** Off by default (`CLAUDE.md` hard rule). Only with a decision
  logged in `project_memory.md` for a specific offline game.
- **Online / anti-cheat games.** Never.
