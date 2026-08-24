import subprocess
import sys
from pathlib import Path

from app import __version__


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_version_is_defined() -> None:
    assert __version__ == "0.1.0"


def test_module_cli_prints_version() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "app", "--version"],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    assert result.stdout.strip() == __version__
    assert result.stderr == ""


def test_module_cli_rejects_unknown_argument() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "app", "--not-a-real-option"],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode != 0
    assert "unrecognized arguments: --not-a-real-option" in result.stderr
    assert result.stdout == ""
