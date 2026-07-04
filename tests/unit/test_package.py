"""Unit tests for the package."""

import os
import subprocess
import sys
from pathlib import Path

import chip8
from chip8 import CPU, Machine, QuirkProfile, get_quirks


def test_package_exports() -> None:
    assert chip8.__version__ == "1.0.2"
    assert "CPU" in chip8.__all__
    assert "Machine" in chip8.__all__
    assert isinstance(get_quirks("modern"), QuirkProfile)
    assert isinstance(CPU(), CPU)
    assert isinstance(Machine.create(), Machine)


def test_main_module_runs_version() -> None:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(Path(__file__).resolve().parents[2] / "src")
    completed = subprocess.run(
        [sys.executable, "-m", "chip8", "--version"],
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )
    assert completed.returncode == 0
    assert "1.0.2" in completed.stdout
