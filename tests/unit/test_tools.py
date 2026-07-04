"""Unit tests for the Tools module."""

import argparse
import json
from pathlib import Path

import pytest

from chip8.cfg import build_cfg
from chip8.cli import main
from chip8.cpu import CPU
from chip8.disasm import format_disassembly
from chip8.errors import TraceVerificationError
from chip8.keyboard import TerminalKeypad
from chip8.opcode import decode
from chip8.runner import (
    ValidationReport,
    _describe_failure,
    state_mismatches,
    validate_rom,
)
from chip8.trace import TraceWriter, verify_trace


def _trace_state(**overrides: object) -> dict[str, object]:
    state: dict[str, object] = {
        "v": [0] * 16,
        "i": 0,
        "delay_timer": 0,
        "sound_timer": 0,
        "stack": [],
        "pc": 0x202,
        "cycles": 1,
        "awaiting_key": False,
    }
    state.update(overrides)
    return state


def test_disassembly_and_cfg() -> None:
    rom = bytes.fromhex("2206 3001 1200 00EE")
    text = format_disassembly(rom)
    assert "200: 2206  CALL 0x206" in text
    graph = build_cfg(rom)
    assert graph.call_targets == {0x206}
    assert graph.jump_targets == {0x200}
    assert graph.reachable() == {0x200, 0x202, 0x204, 0x206}


def test_cfg_flags_malformed_unresolved_and_dead_code() -> None:
    # 200 jumps to 206; 202 is an unknown opcode; 204 is a dynamic BNNN jump.
    rom = bytes.fromhex("1206 0000 B300 00EE")
    graph = build_cfg(rom)
    assert 0x202 in graph.malformed
    assert graph.unresolved[0x204] == "dynamic BNNN jump"
    assert graph.unresolved[0x206] == "dynamic RET"
    reachable = graph.reachable()
    assert 0x206 in reachable
    assert 0x202 not in reachable  # dead/unreachable
    assert 0x204 not in reachable


def test_cfg_marks_fx0a_as_unresolved() -> None:
    rom = bytes.fromhex("F00A 6001")
    graph = build_cfg(rom)
    assert graph.unresolved[0x200] == "blocking FX0A key wait"
    assert 0x202 in graph.edges[0x200]


def test_cfg_marks_off_rom_jump_targets() -> None:
    rom = bytes.fromhex("1000 6001")
    graph = build_cfg(rom)
    assert graph.unresolved[0x200] == "jump target 0x000 outside ROM image"


def test_cfg_marks_skip_targets_outside_rom() -> None:
    graph = build_cfg(bytes.fromhex("4000"))
    assert "skip targets" in graph.unresolved[0x200]


def test_disassembly_emits_trailing_byte() -> None:
    text = format_disassembly(b"\x60\x01\xab")
    assert "200: 6001  LD V0, 0x01" in text
    assert ".byte 0xAB" in text


def test_validation_report_success_and_json() -> None:
    ok = ValidationReport(
        ["chip8"],
        0,
        "out",
        "",
        timed_out=False,
        final_state={"pc": 0x200, "cycles": 4},
    )
    assert ok.success
    assert '"success": true' in ok.to_json()
    assert not ValidationReport(["chip8"], 1, "", "boom", timed_out=False).success
    assert not ValidationReport(["chip8"], -1, "", "", timed_out=True).success
    assert not ValidationReport(["chip8"], 0, "out", "", timed_out=False).success


def test_cli_version(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc:
        main(["--version"])
    assert exc.value.code == 0
    assert "1.0.2" in capsys.readouterr().out


def test_run_rejects_headless_with_step(tmp_path: Path) -> None:
    rom = tmp_path / "tiny.ch8"
    rom.write_bytes(b"\x60\x01\x12\x00")
    assert main(["run", str(rom), "--headless", "--cycles", "4", "--step"]) == 2


def test_oversize_rom_warning(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    from chip8.memory import MEMORY_SIZE, PROGRAM_START

    rom = tmp_path / "big.ch8"
    rom.write_bytes(b"\x00" * (MEMORY_SIZE - PROGRAM_START + 1))
    assert main(["info", str(rom)]) == 0
    assert "warning" in capsys.readouterr().err.lower()
    assert main(["run", str(rom), "--headless", "--cycles", "1"]) == 2
    assert "warning" in capsys.readouterr().err.lower()
    assert main(["test-rom", str(rom), "--cycles", "1"]) == 1
    assert "warning" in capsys.readouterr().err.lower()


def test_empty_rom_exits_with_error(tmp_path: Path) -> None:
    rom = tmp_path / "empty.ch8"
    rom.write_bytes(b"")
    assert main(["run", str(rom), "--headless", "--cycles", "1"]) == 2
    assert main(["disasm", str(rom)]) == 2
    assert main(["cfg", str(rom)]) == 2


def test_memory_fault_rom_exits_with_error(tmp_path: Path) -> None:
    rom = tmp_path / "fault.ch8"
    rom.write_bytes(bytes.fromhex("aff8 ff55"))
    assert main(["run", str(rom), "--headless", "--cycles", "3"]) == 2


def test_interactive_ctrl_c_exits_130(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    rom = tmp_path / "tiny.ch8"
    rom.write_bytes(bytes.fromhex("6001 1200"))

    class InterruptingKeypad(TerminalKeypad):
        def __enter__(self) -> TerminalKeypad:
            return self

        def poll(self, stream: object | None = None) -> None:
            raise KeyboardInterrupt

    monkeypatch.setattr("chip8.cli.TerminalKeypad", InterruptingKeypad)
    assert main(["run", str(rom)]) == 130


def test_validate_rom_parses_final_snapshot(tmp_path: Path) -> None:
    from chip8.runner import validate_rom

    rom = tmp_path / "tiny.ch8"
    rom.write_bytes(bytes.fromhex("6001 1200"))
    report = validate_rom(rom, cycles=4, timeout=10.0)
    assert report.success
    assert report.final_state is not None
    assert report.final_state["cycles"] == 4


def test_validate_rom_reports_golden_mismatch(tmp_path: Path) -> None:
    rom = tmp_path / "loop.ch8"
    rom.write_bytes(bytes.fromhex("6001 7001 1202"))
    report = validate_rom(rom, cycles=5, expect={"pc": 0x200, "cycles": 5, "v0": 3})
    assert not report.success
    assert report.mismatch_details == ["pc: expected 0x200, got 0x202"]
    assert report.failure_reason is not None
    assert "golden mismatch" in report.failure_reason


def test_validate_rom_verifies_trace_file(tmp_path: Path) -> None:
    rom = tmp_path / "tiny.ch8"
    rom.write_bytes(bytes.fromhex("6001 1200"))
    trace = tmp_path / "nested" / "run.trace"
    report = validate_rom(rom, cycles=2, trace=trace)
    assert report.success
    assert trace.is_file()


def test_state_mismatches_formats_registers() -> None:
    state = {"pc": 0x202, "cycles": 5, "v": [3] + [0] * 15}
    assert state_mismatches(state, {"pc": 0x200}) == ["pc: expected 0x200, got 0x202"]
    assert state_mismatches(state, {"v0": 4}) == ["V0: expected 4, got 3"]


def test_failure_reason_notes_fx0a_timeout() -> None:
    reason = _describe_failure(
        exit_code=-1,
        timed_out=True,
        timeout=1.0,
        stderr="",
        final_state={"awaiting_key": True, "pc": 0x200, "cycles": 99},
        expect=None,
        state_match=True,
        trace_error=None,
    )
    assert reason is not None
    assert "FX0A key wait" in reason


def test_trace_rejects_v1_format(tmp_path: Path) -> None:
    path = tmp_path / "trace.log"
    path.write_text(
        json.dumps({"format": "chip8-trace-v1", "rom_sha256": "00" * 32, "quirks": {}})
        + "\n",
        encoding="utf-8",
    )
    with pytest.raises(TraceVerificationError, match="chip8-trace-v1 is no longer supported"):
        verify_trace(path)


def test_trace_rejects_header_only_file(tmp_path: Path) -> None:
    path = tmp_path / "trace.log"
    writer = TraceWriter.open(path, rom=b"\x60\x01", quirks={"name": "modern"})
    writer.close()
    with pytest.raises(TraceVerificationError, match="no execution records"):
        verify_trace(path)


def test_trace_skips_blank_lines(tmp_path: Path) -> None:
    path = tmp_path / "trace.log"
    before = _trace_state(pc=0x200, cycles=0)
    writer = TraceWriter.open(path, rom=b"\x60\x01", quirks={"name": "modern"})
    writer.record(0x200, 0x6001, before, _trace_state(v=[1] + [0] * 15))
    writer.close()
    text = path.read_text(encoding="utf-8")
    path.write_text(text.replace("\n", "\n\n", 1), encoding="utf-8")
    assert verify_trace(path)[0] == 1


def test_cli_reports_unexpected_error_and_interrupt(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(args: argparse.Namespace) -> int:
        raise RuntimeError("boom")

    def interrupt(args: argparse.Namespace) -> int:
        raise KeyboardInterrupt

    monkeypatch.setattr("chip8.cli.dispatch", boom)
    assert main(["info", "x"]) == 70  # unexpected error -> clean exit, no traceback
    monkeypatch.setattr("chip8.cli.dispatch", interrupt)
    assert main(["info", "x"]) == 130  # Ctrl-C -> conventional 128 + SIGINT


def test_trace_chain_detects_tampering(tmp_path: Path) -> None:
    path = tmp_path / "trace.log"
    before = _trace_state(pc=0x200, cycles=0)
    after = _trace_state(v=[1] + [0] * 15)
    writer = TraceWriter.open(path, rom=b"\x60\x01", quirks={"name": "modern"})
    writer.record(0x200, 0x6001, before, after)
    writer.close()
    assert verify_trace(path)[0] == 1
    lines = path.read_text(encoding="utf-8").splitlines()
    header = json.loads(lines[0])
    assert header["format"] == "chip8-trace-v2"
    record = json.loads(lines[1])
    assert record["before_pc"] == 0x200
    assert record["after_pc"] == 0x202
    assert record["cycles"] == 1
    assert record["awaiting_key"] is False
    record["pc"] = 0x202
    lines[1] = json.dumps(record)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    with pytest.raises(TraceVerificationError):
        verify_trace(path)


def test_trace_verify_cross_checks_rom(tmp_path: Path) -> None:
    rom_bytes = b"\x60\x01\x12\x00"
    rom = tmp_path / "tiny.ch8"
    rom.write_bytes(rom_bytes)
    trace = tmp_path / "trace.log"
    before = _trace_state(pc=0x200, cycles=0)
    writer = TraceWriter.open(trace, rom=rom_bytes, quirks={"name": "modern"})
    writer.record(0x200, 0x6001, before, _trace_state(v=[1] + [0] * 15))
    writer.close()
    assert main(["trace-verify", str(trace), "--rom", str(rom)]) == 0
    other = tmp_path / "other.ch8"
    other.write_bytes(b"\xFF\xFF")
    assert main(["trace-verify", str(trace), "--rom", str(other)]) == 2  # ROM mismatch


def test_trace_rejects_missing_schema_fields(tmp_path: Path) -> None:
    path = tmp_path / "trace.log"
    before = _trace_state(pc=0x200, cycles=0)
    after = _trace_state(v=[1] + [0] * 15)
    writer = TraceWriter.open(path, rom=b"\x60\x01", quirks={"name": "modern"})
    writer.record(0x200, 0x6001, before, after)
    writer.close()
    lines = path.read_text(encoding="utf-8").splitlines()
    record = json.loads(lines[1])
    del record["before_pc"]
    lines[1] = json.dumps(record)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    with pytest.raises(TraceVerificationError, match="missing required trace fields"):
        verify_trace(path)


def test_trace_writer_rejects_incomplete_snapshot(tmp_path: Path) -> None:
    path = tmp_path / "trace.log"
    writer = TraceWriter.open(path, rom=b"\x60\x01", quirks={"name": "modern"})
    with pytest.raises(TraceVerificationError, match="after snapshot missing"):
        writer.record(0x200, 0x6001, _trace_state(pc=0x200, cycles=0), {"pc": 0x202})
    writer.close()


def test_trace_rejects_invalid_field_types(tmp_path: Path) -> None:
    path = tmp_path / "trace.log"
    before = _trace_state(pc=0x200, cycles=0)
    after = _trace_state(v=[1] + [0] * 15)
    writer = TraceWriter.open(path, rom=b"\x60\x01", quirks={"name": "modern"})
    writer.record(0x200, 0x6001, before, after)
    writer.close()
    lines = path.read_text(encoding="utf-8").splitlines()
    record = json.loads(lines[1])
    record["v"] = ["not", "ints"]
    lines[1] = json.dumps(record)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    with pytest.raises(TraceVerificationError, match="field 'v' must be"):
        verify_trace(path)


def test_fx0a_awaiting_key_in_trace_record(tmp_path: Path) -> None:
    path = tmp_path / "trace.log"
    cpu = CPU()
    before = cpu.snapshot()
    cpu.pc += 2
    cpu.execute(decode(0xF00A), 0x200)
    after = cpu.snapshot()
    writer = TraceWriter.open(path, rom=b"\xF0\x0A", quirks={"name": "modern"})
    writer.record(0x200, 0xF00A, before, after)
    writer.close()
    record = json.loads(path.read_text(encoding="utf-8").splitlines()[1])
    assert record["awaiting_key"] is True
    assert verify_trace(path)[0] == 1


def test_trace_detects_header_tampering(tmp_path: Path) -> None:
    path = tmp_path / "trace.log"
    before = _trace_state(pc=0x200, cycles=0)
    writer = TraceWriter.open(path, rom=b"\x60\x01", quirks={"name": "modern"})
    writer.record(0x200, 0x6001, before, _trace_state(v=[1] + [0] * 15))
    writer.close()
    lines = path.read_text(encoding="utf-8").splitlines()
    header = json.loads(lines[0])
    header["rom_sha256"] = "00" * 32  # claim a different ROM
    lines[0] = json.dumps(header, sort_keys=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    with pytest.raises(TraceVerificationError):
        verify_trace(path)

