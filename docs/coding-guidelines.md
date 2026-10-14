# Coding Guidelines — PlayerTwo

The rules every contributor (human or AI) follows. **Read this before writing code.**
If something isn't covered here, match the existing pattern in the folder you're touching.

Companion docs: [`architecture.md`](architecture.md) for _why_ the structure is what it
is, [`git-workflow.md`](git-workflow.md) for branches and PRs, and
`docs/memory/project_memory.md` (untracked) for what's happened so far.

---

## 1. The two rules that outrank everything

**1. PlayerTwo must always be stoppable and harmless.** It drives the real keyboard and
mouse. Every code path that sends input goes through `hands/`, which respects the kill
switch and the foreground-window guard. Nothing calls `pydirectinput` (or any input API)
from anywhere else. Stopping releases every held key. If you're unsure whether something
can leave a key held down, it can; fix it before merging.

**2. The bridge is model-agnostic and game-agnostic.** Model choice is a config value.
Game knowledge (bindings, actions, goals) lives in `profiles/*.yaml`. If you find yourself
writing `if model == "moondream"` outside `brain/`, or a literal `"w"` outside a profile,
stop.

---

## 2. Module boundaries

| Package                | Owns                                                                       | Never                                                     |
| ---------------------- | -------------------------------------------------------------------------- | --------------------------------------------------------- |
| `playertwo.capture`    | Getting frames off the screen, downscaling, change detection.              | Talking to the model. Sending input.                      |
| `playertwo.brain`      | Everything model-specific: prompts, Ollama calls, parsing replies.         | Sending input. Knowing key bindings.                      |
| `playertwo.hands`      | Turning a validated `Action` into input. Clamping. Releasing keys.         | Deciding what to do. Calling the model.                   |
| `playertwo.actions`    | Profile schema, `Decision` schema, loading/validating profiles.            | Side effects. Imports from capture/brain/hands.           |
| `playertwo.safety`     | Kill switch, foreground-window guard.                                      | Business logic.                                           |
| `playertwo.orchestrator` | Threads and wiring: capture → brain → hands.                             | Model or game specifics. Direct input calls.              |
| `playertwo.config`     | Loading and validating `config/config.yaml`.                               | Reading env vars ad hoc elsewhere.                        |

Dependency direction: `actions` and `config` depend on nothing internal. `capture`,
`brain`, `hands`, `safety` may depend on `actions`/`config`. Only `orchestrator` and
`app.py` wire them together.

## 3. Interfaces over implementations

Each moving part is a `Protocol` or ABC with one or more implementations:

- `FrameSource` → `DxcamFrameSource` (real), fakes in tests.
- `GameModel` → `OllamaVisionModel` (real), fakes in tests.
- `InputDriver` → `DirectInputDriver` (real), `RecordingInputDriver` in tests.

Code depends on the interface, never the concrete class, except where `app.py` builds the
real objects. This is what makes the model swappable and the logic testable without a game
running.

## 4. Structure and naming

| Thing              | Style                  | Example                               |
| ------------------ | ---------------------- | ------------------------------------- |
| Modules & packages | `snake_case`           | `change_detector.py`, `brain/`        |
| Classes            | `PascalCase`           | `ChangeDetector`, `GameProfile`       |
| Functions, vars    | `snake_case`           | `build_system_prompt`                 |
| Constants          | `SCREAMING_SNAKE_CASE` | `DEFAULT_KILL_SWITCH`                 |
| Config/profile keys| `snake_case`           | `max_hold_seconds`                    |
| Profile files      | `kebab-case.yaml`      | `simple-walker.yaml`                  |
| Action names       | `snake_case`           | `move_forward`, `turn_left`           |

- **One public class per module** for anything non-trivial. Small private helpers may
  colocate.
- **Every package has an `__init__.py` that re-exports its public API** (`__all__`).
  Import from the package, not from nested modules: `from playertwo.capture import
  ChangeDetector`.
- **Package = unit of cohesion.** Files that always change together belong together.
- Imports are sorted by ruff (stdlib, third-party, first-party). Never relative imports
  across packages.

## 5. Typing

- **`mypy --strict` passes, always.** No `Any`, no bare `# type: ignore` (if unavoidable,
  use a specific code and a comment saying why).
- **Pydantic at every boundary**: model replies, `config.yaml`, profile files. Define the
  schema once; never re-declare the same shape as a dict.
- Frames are `Frame = NDArray[np.uint8]` (H×W×3, RGB). Use the alias, not raw arrays.
- Prefer frozen Pydantic models / `@dataclass(frozen=True)` for values passed between
  threads. Immutable data needs no lock.

## 6. Threads and timing

- Capture, brain and hands each run on their own thread (Phase 3).
- **Hand-offs use single-slot containers** (`queue.Queue(maxsize=1)` with drop-oldest, or
  a lock-guarded "latest value"). Never an unbounded queue: a backlog of stale actions is
  worse than no action.
- **No shared mutable state without a lock.** Prefer passing immutable values.
- Every loop checks a shared `threading.Event` for shutdown. No `while True` without one.
- Use `time.monotonic()` for durations, never `time.time()`.
- Every blocking call (model request, queue get) has a timeout.

## 7. Model output handling

- The brain returns a `Decision`, never raw text. Parsing failures are logged at WARNING
  and become `Decision.wait()`.
- An action name not in the active profile becomes `wait`.
- Durations from the model are clamped to the profile's limits in `hands`, even if `brain`
  already validated them. Defence in depth: hands must be safe on its own.

## 8. Errors and logging

- Use `logging` (module-level `logger = logging.getLogger(__name__)`). **No `print`**
  outside the CLI entry point.
- Log one line per decision at DEBUG (action, latency). Per-frame logging at INFO will
  drown everything.
- Don't catch broad `Exception` except at a thread's top level, where it's logged and the
  loop shuts down cleanly (releasing keys).
- Fail fast on bad config/profiles at startup with a clear message, not mid-game.

## 9. Windows-only dependencies

`dxcam`, `pydirectinput` and `keyboard` are imported **inside** the concrete classes that
need them, never at module top level. Everything else (schemas, prompts, executor logic,
change detection) must import and test on any OS. CI runs on Windows anyway.

## 10. Tests

- `tests/` mirrors `src/playertwo/`: `tests/hands/test_executor.py` tests
  `playertwo/hands/executor.py`.
- Pure logic gets unit tests: schemas, clamping, prompt building, change detection.
- Anything touching real hardware (capture, input, Ollama) is tested through fakes, and
  verified live by hand. The PR's "How to verify" says how.
- A bug fix comes with a test that fails without it, where that's possible.

## 11. Config and profiles

- `config/config.yaml` holds machine/runtime settings (model, capture size, safety keys).
- `profiles/<game>.yaml` holds everything about a game. Adding a game = adding a file.
- Both are validated at startup by `python -m playertwo --check`. Keep it passing.

## 12. Sources

- [Ollama API](https://github.com/ollama/ollama/blob/main/docs/api.md)
- [dxcam](https://github.com/ra1nty/DXcam)
- [pydirectinput](https://github.com/learncodebygaming/pydirectinput)
- [Pydantic v2](https://docs.pydantic.dev/latest/)
- [ruff](https://docs.astral.sh/ruff/) · [mypy](https://mypy.readthedocs.io/)
