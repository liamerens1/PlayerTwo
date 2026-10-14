import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# CLAUDE.md phase table row: | 4     | `feat/testbed/4`        | ... | Next    |
TABLE_ROW = re.compile(r"^\|\s*(\d+)\s*\|\s*`([^`]+)`\s*\|.*\|\s*(\w+)\s*\|\s*$", re.MULTILINE)
# roadmap.md phase heading: ### 4. Testbed game ... — `feat/testbed/4`
HEADING = re.compile(r"^### (\d+)\. .+ — `([^`]+)`\s*$", re.MULTILINE)
ROADMAP_STATUS = re.compile(r"^- \*\*Status:\*\* (.+)$", re.MULTILINE)


def _claude_table() -> dict[int, tuple[str, str]]:
    text = (ROOT / "CLAUDE.md").read_text(encoding="utf-8")
    return {int(n): (branch, status) for n, branch, status in TABLE_ROW.findall(text)}


def _roadmap() -> dict[int, tuple[str, bool]]:
    text = (ROOT / "docs" / "roadmap.md").read_text(encoding="utf-8")
    phases: dict[int, tuple[str, bool]] = {}
    sections = HEADING.split(text)[1:]  # [n, branch, body, n, branch, body, ...]
    for n, branch, body in zip(sections[::3], sections[1::3], sections[2::3], strict=True):
        status = ROADMAP_STATUS.search(body)
        assert status is not None, f"roadmap phase {n} has no status line"
        phases[int(n)] = (branch, "done" in status.group(1).lower())
    return phases


def test_roadmap_and_claude_md_list_the_same_phases_and_branches() -> None:
    table = _claude_table()
    roadmap = _roadmap()
    assert table, "CLAUDE.md phase table not found"
    assert {n: branch for n, (branch, _) in table.items()} == {
        n: branch for n, (branch, _) in roadmap.items()
    }


def test_roadmap_and_claude_md_agree_on_what_is_done() -> None:
    table = _claude_table()
    for n, (_, roadmap_done) in _roadmap().items():
        assert (table[n][1] == "Done") == roadmap_done, f"phase {n} status differs"


def test_feature_branches_end_in_their_phase_number() -> None:
    for n, (branch, _) in _claude_table().items():
        assert branch.startswith("feat/") and branch.endswith(f"/{n}"), branch
