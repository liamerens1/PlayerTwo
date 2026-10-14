# Architecture — PlayerTwo

Why the structure is what it is. Read before changing structure.

---

## What PlayerTwo is

A bridge between a game running on this PC and a vision model running on this PC. The
model sees the screen and picks an action; PlayerTwo performs it with real input.

## Why local, not a cloud model

A cloud model (Claude, GPT, etc.) has to round-trip every frame over the internet to a
data centre and back. That's one to several seconds per decision, and frames pile up
faster than they can be answered. Real-time play is impossible that way.

A model on this machine removes the network entirely. The limit becomes GPU inference
time instead, which is much smaller and which we can trade against model quality.

## The loop

```
  CAPTURE  --frame-->  BRAIN (swappable)  --decision-->  HANDS
  (dxcam)              (Ollama vision model)              (pydirectinput)
     ^                                                        |
     +------------------- ORCHESTRATOR (threads) -------------+
                         SAFETY: kill switch + window guard wrap HANDS
```

1. **Capture** grabs the newest frame of the game window only (its client area, from
   whichever monitor shows it), downscales it (~640 px wide), and only passes it on when
   it has meaningfully changed.
2. **Brain** turns a frame + the active profile + the short-term memory into one
   `Decision` (an action name from the profile, plus an optional reason).
3. **Hands** looks the action up in the profile and performs it (hold a key, press a key,
   move the mouse), clamped to the profile's limits.
4. **Orchestrator** runs those on separate threads, connected by single-slot hand-offs,
   and pauses capture and brain while the game isn't focused.
5. **Safety** sits in front of hands: no kill switch, no input; wrong window, no input.

## Short-term memory (Tier 1)

A frozen model repeats the same mistake forever, so PlayerTwo tells it what it just did.
After hands performs an action it waits `memory.settle_seconds`, compares the screen with
the one from just before the action, and records (action, short reason, screen changed
or not) in a ring of the last `memory.size` actions (`playertwo.memory`). The brain puts
that list, one short line each (`- turn_left -> screen changed`), into the per-frame
prompt; the system prompt stays the same every call. **The model's own past reasons are
left out of the prompt:** qwen3-vl 2B copied them word for word and repeated the old
action with the target in plain view (level 1 fell from 20/20 to 1/19). The **stuck detector** adds a hint when the same action ran
`memory.stuck_repeats` times in a row without changing the screen (walking into a wall).
Only performed actions are recorded: dropped (stale, unfocused) ones never happened.
`--no-memory` turns it off, which is how its effect is measured on the testbed. The data
types (`History`, `PastAction`) live in `actions`, so the brain reads them without
depending on the orchestrator.

## The testbed

`testbed/` is a small Ursina game made for measuring PlayerTwo: reach the yellow cube,
five levels, scored episodes written as JSON lines. It is deliberately **not** part of
`playertwo`: neither package imports the other (a test enforces it), so PlayerTwo plays
it exactly as it would a commercial game, through the screen, keyboard and mouse. Its
movement, collisions and outcomes are pure logic (`testbed/physics.py`,
`testbed/episode.py`), so levels are proven winnable in unit tests by a path-following
autopilot; only `testbed/game.py` touches Ursina.

## Brain vs. hands

The model decides the **what** ("move_forward", "turn_left", "interact"). Local code
decides the **how** (hold W for 0.8 s, move the mouse 150 px). Asking a model for every
keypress would cap play at the model's decision rate; letting each decision be a short
behaviour keeps the character moving smoothly while the next decision is computed.

## Why the model is swappable

On an 8 GB card, the trade-off between smart and fast is the central constraint:

| Model         | ~VRAM (Q4) | Role                                     |
| ------------- | ---------- | ---------------------------------------- |
| Qwen3-VL 2B   | ~1.9 GB    | Start here. ~0.6 s/decision, crude play. |
| Qwen3-VL 4B   | ~3.3 GB    | Step up. Modern, long context.           |
| Qwen2.5-VL 7B | ~5–6 GB    | Smarter, slower, tight fit.              |
| MiniCPM-V 8B  | ~6 GB      | Alternative.                             |

Use **non-thinking ("instruct") tags**, such as `qwen3-vl:2b-instruct`. Thinking variants
write paragraphs of reasoning before every answer, and Ollama's `think: false` didn't stop
it for `qwen3-vl:2b`. Moondream, the original starter, returns garbage on Ollama 0.40.x,
even for text-only prompts, so it was dropped.

Replies are constrained with a JSON schema (`format=`) whose `action` field is an enum of
the profile's action names, and whose `reason` has a `maxLength`. The model can't produce
an unknown action or run out of tokens mid-JSON. Replies are still validated afterwards.
A missing model or a stopped Ollama server raises `BrainUnavailableError` (fail fast); a
bad reply, a timeout or a server error becomes `wait`.

The right answer changes with the game, the hardware and next month's model releases. So
`GameModel` is an interface, Ollama serves whichever model `config.yaml` names, and nothing
outside `brain/` knows the difference.

## Why actions are per-game profiles

Every game has different controls and needs. A walking-sim needs four actions; a game with
combat needs twenty. Hardcoding a set would either be too small for later games or too big
(and confusing) for a small model on the first one.

A profile (`profiles/<game>.yaml`) declares:

- the goal, given to the model in its prompt;
- the allowed actions, each with a type (`hold`, `press`, `mouse`, `wait`) and parameters;
- limits like `max_hold_seconds`.

The same profile feeds both the **prompt** (so the model only chooses valid actions) and
**hands** (so it knows how to perform them). Fewer actions = easier choices for a small
model, more reliable output, easier debugging. Start minimal; add actions as games demand.

## Why threads and single-slot hand-offs

If capture waited for the model, the game would be sampled only as fast as the model
thinks. If actions queued up, the character would act on what the screen looked like
seconds ago. So every stage always works on the **newest** value and old ones are dropped.

## Act, then look (`loop.wait_for_result`, on by default)

Capture never waits, but the **brain** does: after a decision it waits until hands has
performed it and `loop.settle_seconds` has passed, then decides on the screen as it is
at that moment. Found the hard way on the testbed: when the brain decided while the last
action was still running, each decision saw the screen from *before* that action, so the
model repeated turns past the target and spun in circles. Each step now takes decision +
action + settle (about 1–1.6 s with a 0.8 s hold), but every decision sees what its last
action did. The pipelined behaviour is still available with `wait_for_result: false`.
Keeping a key held across decisions that repeat the same action ("action persistence")
is planned for Phase 6.

## Safety model

- **Kill switch** (F12 by default) via a global hotkey. Sets the shutdown event; hands
  releases every key it ever pressed.
- **Foreground-window guard**: hands checks the focused window's owning executable against
  `safety.target_process` (and its title against `safety.target_window`, if set) before
  every action and throughout every hold. Terminal and shell windows never match, because
  their titles contain the command line that started PlayerTwo.
- **Pause on focus loss**: while the game isn't the foreground window, capture and the
  brain idle too (frames captured before the pause are discarded), so the model doesn't
  take GPU time from whatever is in front, and nothing stale is acted on afterwards.
- **Validation**: model output is untrusted; anything invalid is `wait`.
- **Scope**: offline single-player games only. No anti-cheat, no online play.

## Deferred, with reasons

- **Fine-tuned / specialised model**: the long-term route to good real-time play. Needs
  recorded gameplay first (Phase 9); imitation learning is Phase 10. Reinforcement
  learning is parked: see [`roadmap.md`](roadmap.md#parked).
- **Structured game state** (mod APIs, logs): game-specific; added per game when available.
- **Game memory reading**: off by default (see `CLAUDE.md`).

## Known constraints

- Roughly 1–5 decisions/second depending on model and frame size.
- Exclusive fullscreen may not capture: use borderless windowed.
- Some games only accept input when PlayerTwo runs as administrator.
- 16 GB system RAM is the first pinch point under load.
