# Roadmap — PlayerTwo

Where PlayerTwo is going, phase by phase. **This is the single source of truth for
direction**; the original planning doc ("Local AI Game-Playing Bridge — Build Plan") is
superseded. `CLAUDE.md`'s phase table is the short version of this document; **the two
must always match** (same numbers, names and branches).
Change the order only with Liam's OK, and record the change in
`docs/memory/project_memory.md`.

Each phase has a goal, a **done bar** (measurable where possible) and a status. Bars
marked _(proposed)_ haven't been agreed yet; confirm them before the phase starts.

**Memory and learning tiers.** These come up in several phases:

| Tier | What                                                                   | Phase    |
| ---- | ---------------------------------------------------------------------- | -------- |
| 1    | Short-term memory: recent decisions carried into the next prompt.      | 4        |
| 2    | Lessons journal: one-line lessons per game, learned from failures.     | 8        |
| 3    | Imitation learning: fine-tune a small vision model on recorded play.   | 11       |
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
  - **Testbed game** (`testbed/`, `python -m testbed --level N`): a tiny Ursina
    third-person game built for a 2B vision model at 640 px. A capsule character, a big
    yellow cube to reach, flat contrasting colours. PlayerTwo plays it like any other game
    (screen in, keyboard and mouse out; neither package imports the other) and it scores
    every episode: success on touching the cube, death on falling, timeout. Results are
    one JSON line per episode; `scripts/score_testbed.py` summarises them. Levels:
    1 open field, 2 cube at a random angle (often off-screen), 3 a wall in the way,
    4 several obstacles, 5 a pit and unfenced edges. Seeded, so runs repeat.
  - **Tier 1 short-term memory:** the last 8 performed actions (action, short reason,
    whether the screen changed) in each prompt, plus a stuck detector: the same action
    3 times with no screen change adds a "you are probably stuck" hint.
  - **Phase 3 review items:** capture only the game window (right monitor, follows
    moves); pause capture and inference while the game isn't focused; build capture and
    the kill switch inside `app.py`'s `try` so the model is always unloaded; measure VRAM
    with the testbed and the model loaded together.
- **Done bar:** **level 1 success rate measured, with and without Tier 1 memory**, over
  the same number of episodes (20 each, same seeds). Level 2 measured the same way.
- **Status:** ✅ done. Baseline (qwen3-vl:2b-instruct, 640 px, act-then-look, seeds
  1–20):

  | Level | Memory | Success | Median time | Time-outs | Decision |
  | ----- | ------ | ------- | ----------- | --------- | -------- |
  | 1     | on     | 20/20   | 5.8 s       | 0         | 0.71 s   |
  | 1     | off    | 20/20   | 6.4 s       | 0         | 0.67 s   |
  | 2     | on     | 1/20    | 5.0 s       | 19        | 0.72 s   |
  | 2     | off    | 1/20    | 4.9 s       | 19        | 0.59 s   |

  Found on the way: deciding while the last action still ran made the model repeat
  turns (fixed by deciding only after each action's result is on screen), and putting
  the model's own reasons into its memory made it copy them (1/19 on level 1; reasons
  are now left out). On level 2 the 2B model can't reliably tell which way to turn:
  without memory it mostly walks forward blindly, with memory it turns more but still
  rarely lines up. That is the bar Phase 5's bigger models have to beat.

### 5. Model upgrades — `feat/model-upgrades/5`

- **Goal:** try `qwen3-vl:4b-instruct` and `qwen2.5vl:7b` against the 2B baseline.
- **Done bar:** for each model, testbed **success rate per level**, **decisions/s**, and
  **VRAM used while a game is running**, recorded side by side, and a default model
  chosen from them.
- **Status:** ✅ done. **Default model stays `qwen3-vl:2b-instruct`:** the bigger models
  score the same on the testbed, are slower and leave less VRAM for a game. Testbed,
  act-then-look, seeds 1–20, VRAM next to the testbed (8,192 MiB card):

  | Model                | L1 mem on | L1 mem off | L2         | Decision | Peak GPU  |
  | -------------------- | --------- | ---------- | ---------- | -------- | --------- |
  | qwen3-vl:2b-instruct | 20/20     | 20/20      | 1/20, 1/20 | ~0.7 s   | ~4.3 GB   |
  | qwen3-vl:4b-instruct | 19/20\*   | 20/20      | 2/20 (on)  | ~0.83 s  | ~5.8 GB   |
  | qwen2.5vl:7b         | 19/20\*   | 20/20      | 1/20 (off) | ~1.05 s  | ~7.7 GB   |

  \*Episode 1 lost to cold-start time-outs, since fixed. Bigger models don't fix level 2:
  every model sees the cube but picks the wrong turn (→ Phase 6). The 7B leaves no room
  for a real game. Built: `--model`, `--stats-json`, `scripts/run_testbed_matrix.py`
  (models × levels × memory, one table with peak GPU memory), validated CLI overrides,
  `loop.max_decision_age_seconds` 1.5 → 5 s, a warm-up that makes one throwaway
  decision, and `brain.host` 127.0.0.1 (Windows "localhost" cost about 2 s per new
  connection).

### 6. Look, then steer — `feat/look-steer/6`

- **Goal:** split seeing from acting. The model answers only "is the target visible, and
  where is it on screen?"; plain code turns that into the profile's actions (search
  towards where it was last seen, turn towards it, walk when it's centred). The target
  and the action mapping live in the profile (`target:`), so the code stays
  game-agnostic. Falls back to the model picking the action when stuck (walls).
  1. Offline perception test (no input): testbed frames graded against the yellow pixels;
     visible/not-visible accuracy, position error, false sightings and latency per model
     and per way of asking (native box, left/centre/right, 0-100 x).
  2. Build: profile `target:`, `GameModel.locate()`, a pure steering module, loop switch.
  3. Measure on the testbed against "model picks the action".
- **Done bar** _(proposed)_: level 2 success rate with look-then-steer measured for each
  model against the Phase 4/5 baseline (about 5%), same seeds; levels 3–5 measured too.
- **Status:** ⏭ next. Added 2026-10-17 (Liam, option A) after level 2 showed the
  models see the cube but pick the wrong turn. **Step 1 done** (testbed `--survey`, 153
  frames graded on the yellow pixels): asked for a box as JSON, qwen3-vl 2B gets
  visible/not visible right 152/153 with no false sightings and the steering side right
  102/103, position error under 1% of the width, 0.61 s; 4B is as accurate at 0.87 s.
  Asking left/centre/right is much worse (41 false sightings for 2B). qwen2.5vl's boxes
  use a different coordinate space (about 1,200 px wide). Step 2 uses 2B + box JSON.

### 7. Optimise — `feat/optimize/7`

- **Goal:** frame size, change detection, action persistence (keep a key held while
  the next decision repeats it: with act-then-look the character currently walks 0.8 s,
  then stands about 0.9 s while the next decision is made).
- **Done bar:** every change is judged on testbed numbers. One is kept only if it improves
  success rate or decisions/s without making the other worse _(proposed)_.
- **Status:** planned. Known lever: image tokens are about 70% of decision time
  (0.38 of 0.56 s at 640 px).

### 8. Lessons journal (Tier 2) — `feat/lessons/8`

- **Goal:** detect deaths and failures, write one-line lessons per game, and feed them
  into the prompt. Testbed deaths are the first signal.
- **Done bar:** **level 5 (pit) success rate improves across runs** as lessons
  accumulate.
- **Status:** planned.

### 9. First real game — `feat/first-game/9`

- **Goal:** a profile and prompt iteration for **A Short Hike** (fallback:
  **SuperTuxKart**). Offline, single-player, no anti-cheat.
- **Done bar** _(proposed)_: reaches a defined in-game goal in a measured share of
  attempts. The goal and target rate are agreed when the phase starts.
- **Status:** planned.

### 10. Recording — `feat/recording/10`

- **Goal:** record frame + human input pairs while Liam plays.
- **Done bar** _(proposed)_: a documented dataset format; frames and inputs time-aligned
  and replayable; enough hours recorded for Phase 11 (amount agreed then).
- **Status:** planned.

### 11. Imitation learning (Tier 3) — `feat/imitation/11`

- **Goal:** LoRA fine-tune a small vision model on the Phase 10 recordings.
- **Done bar** _(proposed)_: the fine-tuned model beats the prompt-only model's testbed
  success rate at equal or better decisions/s.
- **Status:** planned.

---

## Game ladder (after Phase 11)

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
