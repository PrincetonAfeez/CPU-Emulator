"""Integration tests for the CLI."""

import json
import os
import subprocess
import sys
from pathlib import Path

from chip8.machine import DeterministicClock, Machine
from chip8.quirks import get_quirks
from chip8.runner import validate_rom

BUNDLED_ROM = Path(__file__).parents[1] / "roms" / "increment-loop.ch8"
OPCODE_SMOKE_ROM = Path(__file__).parents[1] / "roms" / "opcode-smoke.ch8"
CLASSIC_ROM = Path(__file__).parents[1] / "roms" / "classic-fx55.ch8"


def _src_env() -> dict[str, str]:
    return {**os.environ, "PYTHONPATH": str(Path(__file__).parents[2] / "src")}


def test_tiny_rom_runs_for_k_cycles() -> None:
    # V0 = 1; V0 += 1; jump back to ADD
    machine = Machine.create(clock=DeterministicClock(), seed=0)
    machine.cpu.load_rom(bytes.fromhex("6001 7001 1202"))
    machine.run_headless(5, speed=600)
    assert machine.cpu.v[0] == 3
    assert machine.cpu.pc == 0x202


def test_cli_info_and_headless_run(tmp_path: Path) -> None:
    rom = tmp_path / "tiny.ch8"
    rom.write_bytes(bytes.fromhex("6001 1200"))
    env = _src_env()
    info = subprocess.run(
        [sys.executable, "-m", "chip8", "info", str(rom)],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    assert info.returncode == 0
    assert "SHA-256:" in info.stdout
    run = subprocess.run(
        [
            sys.executable,
            "-m",
            "chip8",
            "run",
            str(rom),
            "--headless",
            "--cycles",
            "4",
        ],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    assert run.returncode == 0
    assert "Completed 4 cycles" in run.stdout

    validation = subprocess.run(
        [
            sys.executable,
            "-m",
            "chip8",
            "test-rom",
            str(rom),
            "--cycles",
            "4",
        ],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    assert validation.returncode == 0
    assert '"success": true' in validation.stdout
    payload = json.loads(validation.stdout)
    assert payload["final_state"]["cycles"] == 4


def test_cli_disasm_cfg_and_trace(tmp_path: Path) -> None:
    rom = tmp_path / "loop.ch8"
    rom.write_bytes(bytes.fromhex("6001 7001 1202"))
    trace = tmp_path / "run.trace"
    env = _src_env()

    disasm = subprocess.run(
        [sys.executable, "-m", "chip8", "disasm", str(rom)],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    assert disasm.returncode == 0
    assert "LD V0, 0x01" in disasm.stdout

    cfg = subprocess.run(
        [sys.executable, "-m", "chip8", "cfg", str(rom)],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    assert cfg.returncode == 0
    assert "Instruction nodes:" in cfg.stdout
    assert "dynamic BNNN jump" not in cfg.stdout

    run = subprocess.run(
        [
            sys.executable,
            "-m",
            "chip8",
            "run",
            str(rom),
            "--headless",
            "--cycles",
            "3",
            "--trace",
            str(trace),
        ],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    assert run.returncode == 0
    assert trace.is_file()

    verified = subprocess.run(
        [sys.executable, "-m", "chip8", "trace-verify", str(trace), "--rom", str(rom)],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    assert verified.returncode == 0
    assert "Trace verified:" in verified.stdout


def test_bundled_increment_loop_rom_smoke_test() -> None:
    assert BUNDLED_ROM.is_file()
    report = validate_rom(
        BUNDLED_ROM,
        cycles=5,
        expect={"pc": 0x202, "cycles": 5, "v0": 3},
    )
    assert report.success
    assert report.final_state is not None
    assert report.final_state["awaiting_key"] is False


def test_bundled_opcode_smoke_rom() -> None:
    assert OPCODE_SMOKE_ROM.is_file()
    machine = Machine.create(clock=DeterministicClock(), seed=0)
    machine.cpu.load_rom(OPCODE_SMOKE_ROM.read_bytes())
    machine.run_headless(3, speed=600)
    assert machine.cpu.v[0] == 4
    assert machine.cpu.pc == 0x202
    report = validate_rom(
        OPCODE_SMOKE_ROM,
        cycles=3,
        expect={"pc": 0x202, "cycles": 3, "v0": 4},
    )
    assert report.success


def test_cli_test_rom_expect_flags() -> None:
    env = _src_env()
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "chip8",
            "test-rom",
            str(BUNDLED_ROM),
            "--cycles",
            "5",
            "--expect-pc",
            "0x202",
            "--expect-cycles",
            "5",
            "--expect-v0",
            "3",
        ],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["success"] is True
    assert payload["state_match"] is True

    mismatch = subprocess.run(
        [
            sys.executable,
            "-m",
            "chip8",
            "test-rom",
            str(BUNDLED_ROM),
            "--cycles",
            "5",
            "--expect-pc",
            "0x200",
        ],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    assert mismatch.returncode == 1
    bad = json.loads(mismatch.stdout)
    assert bad["success"] is False
    assert bad["state_match"] is False


def test_bundled_classic_fx55_increments_i() -> None:
    assert CLASSIC_ROM.is_file()
    machine = Machine.create(
        clock=DeterministicClock(), seed=0, quirks=get_quirks("classic")
    )
    machine.cpu.load_rom(CLASSIC_ROM.read_bytes())
    machine.run_headless(4, speed=600)
    assert machine.cpu.i == 0x302
    assert machine.cpu.memory.read(0x300) == 1
    assert machine.cpu.memory.read(0x301) == 2


def test_cli_test_rom_classic_quirks_smoke() -> None:
    env = _src_env()
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "chip8",
            "test-rom",
            str(CLASSIC_ROM),
            "--cycles",
            "4",
            "--quirks",
            "classic",
        ],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["success"] is True


def test_cli_test_rom_prints_failure_reason(tmp_path: Path) -> None:
    rom = tmp_path / "loop.ch8"
    rom.write_bytes(bytes.fromhex("6001 7001 1202"))
    env = _src_env()
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "chip8",
            "test-rom",
            str(rom),
            "--cycles",
            "5",
            "--expect-pc",
            "0x200",
        ],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    assert result.returncode == 1
    assert "golden mismatch" in result.stderr
    assert "0x202" in result.stderr
