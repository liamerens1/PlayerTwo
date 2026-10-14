"""The testbed and PlayerTwo only meet through the screen, keyboard and mouse."""

import ast
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _imported_modules(folder: Path) -> set[str]:
    modules: set[str] = set()
    for path in folder.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                modules.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
                modules.add(node.module.split(".")[0])
    return modules


def test_playertwo_never_imports_the_testbed() -> None:
    assert "testbed" not in _imported_modules(ROOT / "src" / "playertwo")


def test_testbed_never_imports_playertwo() -> None:
    assert "playertwo" not in _imported_modules(ROOT / "testbed")


def test_testbed_logic_imports_without_ursina() -> None:
    # Only testbed.game may import Ursina (lazily), so CI without the extra still tests
    # everything else. A fresh interpreter, so other tests' imports don't count.
    code = (
        "import sys; import testbed.cli, testbed.levels, testbed.results, testbed.autopilot; "
        "bad = [m for m in ('ursina', 'panda3d') if m in sys.modules]; print(bad); "
        "sys.exit(1 if bad else 0)"
    )
    run = subprocess.run([sys.executable, "-c", code], cwd=ROOT, capture_output=True, text=True)
    assert run.returncode == 0, run.stdout + run.stderr
