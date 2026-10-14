# Git Workflow — PlayerTwo

How code gets from an idea to `main`. Applies to every contributor, human or AI.

---

## 1. Branches

| Branch                             | Purpose                                                       | Who commits                  |
| ---------------------------------- | ------------------------------------------------------------- | ---------------------------- |
| `main`                             | Stable milestones only. What you'd show someone.              | Nobody directly. PR from `dev`. |
| `dev`                              | Integration branch. All finished work lands here first.       | Nobody directly. PRs only.   |
| `feat/<short-description>/<phase>` | New functionality, tied to a phase in `CLAUDE.md`.            | Anyone, via PR into `dev`.   |
| `fix/<short-description>`          | Bug fixes, at any time, not tied to a phase.                  | Anyone, via PR into `dev`.   |

Naming rules:

- `<short-description>` is **kebab-case**, 2–4 words: `capture-input`, `kill-switch-race`.
- `<phase>` is the phase **number** from the table in `CLAUDE.md`: `feat/brain/2`.
- Work that spans phases gets one branch per phase, not one long-lived branch.

Examples:

```
feat/scaffold/0
feat/capture-input/1
feat/brain/2
fix/stuck-w-key
fix/ollama-timeout
```

> Git can't hold both `feat/brain` and `feat/brain/2` as branches (one is a file, the other
> a folder under `refs/heads`). Always include the phase number on `feat/` branches and
> this never comes up.

## 2. Flow

```powershell
git checkout dev
git pull
git checkout -b feat/capture-input/1
# ...work, commit in meaningful units, push...
git push -u origin feat/capture-input/1
# open a PR into dev
```

- `dev` → `main` only at a stable milestone (usually a phase or two landing), via PR.
- Rebase your branch on `dev` if it falls behind; don't merge `dev` into it repeatedly.
- Delete the branch after its PR merges.

## 3. Commits

- **Imperative mood, explain why**: `Clamp hold durations to the profile max so a bad model
  reply can't pin W down`, not `updated executor`.
- **Push after each meaningful unit of work**: a working component, a fix, a config change.
  Don't let a session pile up into one blob commit.
- **Ask before committing** (AI contributors).
- **No `Co-Authored-By` trailers.**
- **Before every commit**, add a dated entry to `docs/memory/project_memory.md`.

## 4. Pull requests

### Title

Conventional, lowercase type, short description:

```
feat: screen capture and input driver
feat: ollama brain with moondream
fix: stuck w key after kill switch
```

Allowed types: `feat`, `fix`. Use `chore:` or `docs:` only for PRs that change nothing but
tooling or documentation.

### Description

Full Markdown, using `.github/pull_request_template.md`. It should let someone understand
the PR **without reading the diff first**:

- **Summary**: one or two sentences.
- **What changed**: every meaningful change, grouped by area, as bullets. New files,
  removed files, behaviour changes, config/profile changes, dependency changes.
- **Why**: the reasoning and any decisions taken, linked to the memory entry.
- **How to verify**: concrete steps and the expected result. "Run `python -m playertwo
  --check`, it prints the profile's 5 actions" — not "tested locally".
- **Known issues / follow-ups**: anything deliberately left out.
- **Checklist**: ticked honestly.

### Target

PRs target **`dev`**. The only PRs into `main` come from `dev`.
