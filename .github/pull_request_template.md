<!--
Title: `feat: short description` or `fix: short description` (lowercase type).
Target: `dev`. See docs/git-workflow.md.
Someone should understand this PR from the description alone, before reading the diff.
-->

## Summary

<!-- One or two sentences: what this PR does. -->

## What changed

<!-- Every meaningful change, grouped by area (capture / brain / hands / safety / actions /
config / profiles / tooling / docs). New and removed files, behaviour changes, config or
profile changes, dependency changes. -->

### <!-- area -->

-

## Why

<!-- The reasoning and any decisions taken. Point to the dated entry in
docs/memory/project_memory.md. -->

## How to verify

<!-- Concrete steps and the expected result. "Run `python -m playertwo --check`, it prints
the profile's 5 actions", not "tested locally". Anything touching real input or capture
needs a live check, and says what was tested against (Notepad or the testbed; no commercial
game before Phase 8). -->

1. `ruff check .` → `All checks passed!`
2. `ruff format --check .` → all files already formatted
3. `mypy` → `Success: no issues found`
4. `pytest` → all passed
5. `python -m playertwo --check` → config and profile OK

## Known issues / follow-ups

<!-- Anything deliberately left out, known limitations, or work for a later phase. "None" if
none. -->

## Checklist

- [ ] Branch is `feat/<short-description>/<phase>` or `fix/<short-description>`, targeting `dev`
- [ ] `ruff check`, `ruff format --check`, `mypy` (strict) and `pytest` pass locally
- [ ] `python -m playertwo --check` passes
- [ ] CI is green
- [ ] Windows-only libraries are imported lazily
- [ ] All input goes through `hands/` behind the kill switch and window guard
- [ ] Nothing model-specific outside `brain/`, nothing game-specific outside `profiles/`
- [ ] Anything that sends input or captures the screen was live-verified (say against what)
- [ ] Dated entry added to `docs/memory/project_memory.md` before committing
