import subprocess
import sys

WINDOWS_ONLY = ("dxcam", "pydirectinput", "keyboard")


def test_packages_import_without_windows_only_libraries() -> None:
    # Fresh interpreter, so nothing another test imported can hide an eager import.
    code = (
        "import sys, playertwo.capture, playertwo.hands, playertwo.safety, playertwo.app\n"
        f"loaded = [m for m in {WINDOWS_ONLY!r} if m in sys.modules]\n"
        "print(','.join(loaded))\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, check=True, timeout=60
    )
    assert result.stdout.strip() == ""
