"""Optional conformance runs against a user-supplied opcode-test ROM directory."""

from __future__ import annotations

import os
import warnings
from pathlib import Path

import pytest

from chip8.memory import MEMORY_SIZE, PROGRAM_START
from chip8.runner import validate_rom

ROM_DIR_ENV = "CHIP8_CONFORMANCE_ROM_DIR"
MAX_ROM_SIZE = MEMORY_SIZE - PROGRAM_START


def _iter_rom_paths() -> list[Path]:
    raw = os.environ.get(ROM_DIR_ENV)
    if not raw:
        return []
    directory = Path(raw)
    if not directory.is_dir():
        pytest.skip(f"{ROM_DIR_ENV} is not a directory: {directory}")
    roms = sorted(directory.glob("*.ch8"))
    if not roms:
        pytest.skip(f"no .ch8 files found in {directory}")
    return roms


@pytest.mark.skipif(
    not os.environ.get(ROM_DIR_ENV),
    reason=f"set {ROM_DIR_ENV} to a directory of .ch8 ROMs to enable conformance tests",
)
def test_public_roms_run_without_crashing() -> None:
    skipped: list[str] = []
    for rom_path in _iter_rom_paths():
        size = rom_path.stat().st_size
        if size > MAX_ROM_SIZE:
            skipped.append(f"{rom_path.name} ({size} bytes > {MAX_ROM_SIZE})")
            continue
        report = validate_rom(rom_path, cycles=500, timeout=30.0)
        assert report.exit_code == 0, f"{rom_path.name}: {report.stderr}"
        assert report.final_state is not None, rom_path.name
        assert report.success, report.failure_reason or rom_path.name
    if skipped:
        warnings.warn(
            "Skipped oversized conformance ROMs: " + ", ".join(skipped),
            UserWarning,
            stacklevel=1,
        )
