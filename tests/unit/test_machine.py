"""Unit tests for the Machine module."""

import os
import subprocess
import sys
from pathlib import Path

import pytest

from chip8.debug import changed_fields, format_transition
from chip8.keyboard import TerminalKeypad
from chip8.machine import DeterministicClock, Machine
from chip8.opcode import decode
from chip8.runner import validate_rom


def test_format_transition_reports_changes() -> None:
    before = {
        "pc": 0x200,
        "v": [0] * 16,
        "i": 0,
        "cycles": 0,
        "awaiting_key": False,
    }
    after = {
        "pc": 0x202,
        "v": [1] + [0] * 15,
        "i": 0,
        "cycles": 1,
        "awaiting_key": False,
    }
    changes = changed_fields(before, after)
    assert "v" in changes
    text = format_transition(0x200, decode(0x6001), before, after)
    assert "6001" in text
    assert "v:" in text


def test_run_interactive_step_mode_advances_with_input(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    steps = {"count": 0}

    def fake_input() -> str:
        steps["count"] += 1
        if steps["count"] >= 2:
            raise KeyboardInterrupt
        return ""

    monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr("builtins.input", fake_input)
    machine = Machine.create(
        keypad=TerminalKeypad(), clock=DeterministicClock(), seed=0
    )
    machine.cpu.load_rom(bytes.fromhex("6001 1200"))
    with pytest.raises(KeyboardInterrupt):
        machine.run_interactive(step_mode=True, max_cycles=10)
    assert machine.cpu.cycles >= 1


def test_validate_rom_marks_timeout(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    rom = tmp_path / "tiny.ch8"
    rom.write_bytes(bytes.fromhex("6001 1200"))

    def timeout(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        raise subprocess.TimeoutExpired(cmd="chip8", timeout=0.001)

    monkeypatch.setattr("chip8.runner.subprocess.run", timeout)
    report = validate_rom(rom, cycles=4, timeout=0.001)
    assert report.timed_out
    assert not report.success


def test_validate_rom_checks_expected_snapshot(tmp_path: Path) -> None:
    rom = tmp_path / "loop.ch8"
    rom.write_bytes(bytes.fromhex("6001 7001 1202"))
    ok = validate_rom(rom, cycles=5, expect={"pc": 0x202, "cycles": 5, "v0": 3})
    assert ok.success
    bad = validate_rom(rom, cycles=5, expect={"pc": 0x200, "cycles": 5, "v0": 3})
    assert not bad.success
    assert bad.state_match is False


def test_run_interactive_polls_during_cycle_wait(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    poll_calls: list[int] = []

    class CountingKeypad(TerminalKeypad):
        def __enter__(self) -> TerminalKeypad:
            return self

        def poll(self, stream: object | None = None) -> None:
            poll_calls.append(1)

    monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
    machine = Machine.create(
        keypad=CountingKeypad(), clock=DeterministicClock(), seed=0
    )
    machine.cpu.load_rom(bytes.fromhex("6001 1200"))
    machine.run_interactive(speed=10_000, max_cycles=2)
    assert machine.cpu.cycles == 2
    assert len(poll_calls) >= 2


def test_load_rom_file_reads_bytes(tmp_path: Path) -> None:
    rom_path = tmp_path / "tiny.ch8"
    rom_path.write_bytes(bytes.fromhex("6001"))
    machine = Machine.create(clock=DeterministicClock())
    loaded = machine.load_rom_file(rom_path)
    assert loaded == bytes.fromhex("6001")
    assert machine.cpu.memory.read_word(0x200) == 0x6001


def test_step_updates_timers_from_clock() -> None:
    clock = DeterministicClock(now=0.0)
    machine = Machine.create(clock=clock)
    machine.cpu.load_rom(bytes.fromhex("6001 1200"))
    machine.cpu.timers.delay = 60
    machine.step()
    clock.now = 1.0
    machine.step()
    assert machine.cpu.timers.delay < 60


def test_run_headless_writes_trace_records(tmp_path: Path) -> None:
    from chip8.trace import TraceWriter, verify_trace

    trace = tmp_path / "run.trace"
    machine = Machine.create(clock=DeterministicClock(), seed=0)
    machine.cpu.load_rom(bytes.fromhex("6001 1200"))
    writer = TraceWriter.open(trace, rom=bytes.fromhex("6001 1200"), quirks={"name": "modern"})
    try:
        machine.run_headless(2, trace=writer)
    finally:
        writer.close()
    assert verify_trace(trace)[0] == 2


def test_run_interactive_requires_terminal_keypad() -> None:
    machine = Machine.create(clock=DeterministicClock())
    machine.cpu.load_rom(bytes.fromhex("6001"))
    with pytest.raises(TypeError, match="TerminalKeypad"):
        machine.run_interactive(max_cycles=1)


def test_run_interactive_emits_sound_on_timer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeKeypad(TerminalKeypad):
        def __enter__(self) -> TerminalKeypad:
            return self

    monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
    written: list[str] = []

    def capture_write(text: str) -> int:
        written.append(text)
        return len(text)

    monkeypatch.setattr(sys.stdout, "write", capture_write)
    monkeypatch.setattr(sys.stdout, "flush", lambda: None)
    machine = Machine.create(
        keypad=FakeKeypad(), clock=DeterministicClock(), seed=0
    )
    machine.cpu.load_rom(bytes.fromhex("6101 F118 1200"))
    machine.run_interactive(speed=10_000, max_cycles=2)
    assert any("\a" in chunk for chunk in written)
    assert machine.cpu.timers.sound == 1


def test_enable_ansi_console_on_windows(monkeypatch: pytest.MonkeyPatch) -> None:
    from chip8.machine import enable_ansi_console

    monkeypatch.setattr(os, "name", "nt")
    enable_ansi_console()


def test_real_clock_advances(monkeypatch: pytest.MonkeyPatch) -> None:
    from chip8.machine import RealClock

    clock = RealClock()
    monkeypatch.setattr("chip8.machine.time.monotonic", lambda: 42.0)
    monkeypatch.setattr("chip8.machine.time.sleep", lambda _: None)
    assert clock.monotonic() == 42.0
    clock.sleep(0.5)
