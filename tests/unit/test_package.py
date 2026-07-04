"""Unit tests for the package."""

import os
import subprocess
import sys
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

import pytest

import chip8
from chip8 import CPU, Machine, QuirkProfile, get_quirks


def test_package_exports() -> None:
    assert chip8.__version__ == "2.0.0"
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
    assert "2.0.0" in completed.stdout


def test_package_versions_match() -> None:
    try:
        installed = version("chip8-capstone")
    except PackageNotFoundError:
        pytest.skip("chip8-capstone is not installed")
    assert installed == chip8.__version__
