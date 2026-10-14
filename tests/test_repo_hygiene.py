import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEXT_SUFFIXES = {".md", ".py", ".yaml", ".yml", ".toml", ".txt", ".gitignore", ".gitattributes"}
SKIP_DIRS = {".venv", ".git", ".mypy_cache", ".ruff_cache", ".pytest_cache", "__pycache__"}
CONTROL_BYTES = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def _text_files() -> list[Path]:
    return [
        path
        for path in ROOT.rglob("*")
        if path.is_file()
        and (path.suffix in TEXT_SUFFIXES or path.name in TEXT_SUFFIXES)
        and not SKIP_DIRS.intersection(path.relative_to(ROOT).parts)
    ]


def test_no_control_bytes_in_text_files() -> None:
    # Regression: scripted edits turned "\b" in "scripts\benchmark_brain.py" into a literal
    # backspace (0x08) in CLAUDE.md and README.md.
    found = [
        f"{path.relative_to(ROOT)}:{number}: {line!r}"
        for path in _text_files()
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1)
        if CONTROL_BYTES.search(line)
    ]
    assert found == []
