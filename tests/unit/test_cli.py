"""Unit tests for the CLI module."""

import argparse
import sys
from pathlib import Path

import pytest

from chip8.cli import (
    _build_expect,
    _int_byte,
    _int_literal,
    _positive_float,
    _positive_int,
    _read_rom,
    _warn_if_unloadable,
    build_parser,
    main,
)
from chip8.keyboard import TerminalKeypad


def test_parser_rejects_invalid_numeric_arguments() -> None:
    with pytest.raises(SystemExit):
        build_parser().parse_args(["run", "rom.ch8", "--cycles", "0"])
    with pytest.raises(SystemExit):
        build_parser().parse_args(["test-rom", "rom.ch8", "--timeout", "0"])
    with pytest.raises(SystemExit):
        build_parser().parse_args(["test-rom", "rom.ch8", "--expect-pc", "0x1000"])


def test_type_helpers_validate_ranges() -> None:
    assert _positive_int("3") == 3
    assert _positive_float("1.5") == 1.5
    assert _int_literal("0x202") == 0x202
    assert _int_byte("0xFF") == 255
    with pytest.raises(argparse.ArgumentTypeError):
        _positive_int("0")
    with pytest.raises(argparse.ArgumentTypeError):
        _positive_float("-1")
    with pytest.raises(argparse.ArgumentTypeError):
        _int_literal("-1")
    with pytest.raises(argparse.ArgumentTypeError):
        _int_byte("256")


def test_build_expect_collects_all_register_flags() -> None:
    args = argparse.Namespace(
        expect_pc=0x202,
        expect_cycles=5,
        expect_v0=1,
        expect_v1=2,
        expect_v2=None,
        expect_v3=None,
        expect_v4=None,
        expect_v5=None,
        expect_v6=None,
        expect_v7=None,
        expect_v8=None,
        expect_v9=None,
        expect_va=None,
        expect_vb=None,
        expect_vc=None,
        expect_vd=None,
        expect_ve=None,
        expect_vf=None,
    )
    expect = _build_expect(args)
    assert expect == {"pc": 0x202, "cycles": 5, "v0": 1, "v1": 2}


def test_build_expect_returns_none_when_empty() -> None:
    args = argparse.Namespace(
        expect_pc=None,
        expect_cycles=None,
        **{f"expect_v{nibble}": None for nibble in "0123456789abcdef"},
    )
    assert _build_expect(args) is None


def test_read_rom_missing_file(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        _read_rom(tmp_path / "missing.ch8")


def test_warn_if_unloadable_prints(capsys: pytest.CaptureFixture[str]) -> None:
    from chip8.memory import MEMORY_SIZE, PROGRAM_START

    _warn_if_unloadable(b"\x00" * (MEMORY_SIZE - PROGRAM_START + 1))
    assert "warning" in capsys.readouterr().err.lower()


def test_info_warns_on_odd_rom(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    rom = tmp_path / "odd.ch8"
    rom.write_bytes(b"\x60\x01\xab")
    assert main(["info", str(rom)]) == 0
    assert "odd trailing byte" in capsys.readouterr().out


def test_run_headless_requires_cycles(tmp_path: Path) -> None:
    rom = tmp_path / "tiny.ch8"
    rom.write_bytes(bytes.fromhex("6001 1200"))
    assert main(["run", str(rom), "--headless"]) == 2


def test_run_headless_seed_is_printed(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    rom = tmp_path / "tiny.ch8"
    rom.write_bytes(bytes.fromhex("6001 1200"))
    assert main(["run", str(rom), "--headless", "--cycles", "1", "--seed", "5"]) == 0
    assert "Random seed: 5" in capsys.readouterr().out


def test_run_interactive_seed_note(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    rom = tmp_path / "tiny.ch8"
    rom.write_bytes(bytes.fromhex("6001 1200"))

    class FakeKeypad(TerminalKeypad):
        def __enter__(self) -> TerminalKeypad:
            return self

        def __exit__(self, *_: object) -> None:
            pass

        def poll(self, stream: object | None = None) -> None:
            raise KeyboardInterrupt

    monkeypatch.setattr("chip8.cli.TerminalKeypad", FakeKeypad)
    monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
    assert main(["run", str(rom), "--seed", "5"]) == 130
    err = capsys.readouterr().err
    assert "nondeterministic" in err


def test_run_interactive_without_cycles_note(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    rom = tmp_path / "tiny.ch8"
    rom.write_bytes(bytes.fromhex("6001 1200"))

    class FakeKeypad(TerminalKeypad):
        def __enter__(self) -> TerminalKeypad:
            return self

        def __exit__(self, *_: object) -> None:
            pass

        def poll(self, stream: object | None = None) -> None:
            raise KeyboardInterrupt

    monkeypatch.setattr("chip8.cli.TerminalKeypad", FakeKeypad)
    monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
    assert main(["run", str(rom)]) == 130
    assert "runs until Ctrl+C" in capsys.readouterr().err


def test_debug_errors_shows_traceback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    rom = tmp_path / "tiny.ch8"
    rom.write_bytes(bytes.fromhex("6001 1200"))

    def boom(_: argparse.Namespace) -> int:
        raise RuntimeError("boom")

    monkeypatch.setattr("chip8.cli.dispatch", boom)
    with pytest.raises(RuntimeError, match="boom"):
        main(["run", str(rom), "--headless", "--cycles", "1", "--debug-errors"])


def test_test_rom_writes_report(tmp_path: Path) -> None:
    rom = tmp_path / "tiny.ch8"
    rom.write_bytes(bytes.fromhex("6001 1200"))
    report = tmp_path / "report.json"
    assert main(["test-rom", str(rom), "--cycles", "2", "--report", str(report)]) == 0
    assert report.is_file()
    assert '"success": true' in report.read_text(encoding="utf-8")


def test_trace_verify_without_rom(tmp_path: Path) -> None:
    rom = tmp_path / "tiny.ch8"
    rom.write_bytes(bytes.fromhex("6001 1200"))
    trace = tmp_path / "run.trace"
    assert main(["run", str(rom), "--headless", "--cycles", "1", "--trace", str(trace)]) == 0
    assert main(["trace-verify", str(trace)]) == 0
