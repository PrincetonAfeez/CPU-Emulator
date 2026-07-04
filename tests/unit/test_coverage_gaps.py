"""Cover remaining CLI and CPU edge paths."""

import argparse
import sys
from pathlib import Path

import pytest

from chip8.cli import command_run, main
from chip8.cpu import CPU
from chip8.keyboard import TerminalKeypad
from chip8.runner import _describe_failure, _parse_final_state


def test_command_run_interactive_completes_with_max_cycles(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    rom = tmp_path / "tiny.ch8"
    rom.write_bytes(bytes.fromhex("6001 1200"))

    class FakeKeypad(TerminalKeypad):
        def __enter__(self) -> TerminalKeypad:
            return self

    monkeypatch.setattr("chip8.cli.TerminalKeypad", FakeKeypad)
    monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
    args = argparse.Namespace(
        rom=rom,
        speed=10_000,
        quirks="modern",
        step=False,
        headless=False,
        cycles=1,
        seed=None,
        trace=None,
    )
    assert command_run(args) == 0
    assert "Completed 1 cycles" in capsys.readouterr().out


def test_main_unexpected_error_without_debug_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def boom(_: argparse.Namespace) -> int:
        raise RuntimeError("boom")

    monkeypatch.setattr("chip8.cli.dispatch", boom)
    assert main(["info", "x"]) == 70


def test_cpu_default_random_byte_is_in_range() -> None:
    cpu = CPU()
    assert 0 <= cpu.random_byte() <= 255


def test_parse_final_state_ignores_snapshot_without_cycles() -> None:
    stdout = '{"pc": 514, "v": [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]}\n'
    assert _parse_final_state(stdout) is None


def test_describe_failure_without_snapshot_and_expectations() -> None:
    reason = _describe_failure(
        exit_code=0,
        timed_out=False,
        timeout=1.0,
        stderr="",
        final_state=None,
        expect={"pc": 0x200},
        state_match=False,
        trace_error=None,
    )
    assert reason is not None
    assert "no final CPU snapshot" in reason
