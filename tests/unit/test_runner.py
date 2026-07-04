"""Unit tests for the Runner module."""

import subprocess
from pathlib import Path

import pytest

from chip8.runner import (
    ValidationReport,
    _as_text,
    _describe_failure,
    _parse_final_state,
    _register_mismatch,
    _state_matches,
    state_mismatches,
    validate_rom,
)


def test_as_text_handles_none_and_bytes() -> None:
    assert _as_text(None) == ""
    assert _as_text("hello") == "hello"
    assert _as_text(b"hello") == "hello"
    assert _as_text(b"\xff\xfe") == "\ufffd\ufffd"


def test_parse_final_state_ignores_non_json_lines() -> None:
    stdout = "ROM SHA-256: abc\nnot json\n{\"pc\": 514, \"cycles\": 4}\n"
    state = _parse_final_state(stdout)
    assert state is not None
    assert state["pc"] == 514


def test_parse_final_state_skips_invalid_json() -> None:
    stdout = "{not valid json}\n{\"pc\": 514, \"cycles\": 1}\n"
    state = _parse_final_state(stdout)
    assert state is not None
    assert state["cycles"] == 1


def test_parse_final_state_returns_none_when_missing() -> None:
    assert _parse_final_state("no snapshot here") is None


def test_register_mismatch_without_snapshot() -> None:
    assert _register_mismatch("pc", 0x200, None) is not None


def test_register_mismatch_register_shorthand() -> None:
    registers = [0] * 16
    registers[10] = 5
    state: dict[str, object] = {"v": registers}
    assert _register_mismatch("va", 1, state) == "VA: expected 1, got 5"


def test_state_matches_and_mismatches_are_inverses() -> None:
    state = {"pc": 0x202, "cycles": 3, "v": [1] + [0] * 15}
    expect = {"pc": 0x200, "v0": 2}
    assert not _state_matches(state, expect)
    assert len(state_mismatches(state, expect)) == 2


def test_success_requires_no_failure_reason() -> None:
    report = ValidationReport(
        ["chip8"],
        0,
        '{"pc": 514, "cycles": 4}',
        "",
        False,
        {"pc": 0x202, "cycles": 4},
        True,
        [],
        None,
    )
    assert report.success
    failed = ValidationReport(
        ["chip8"],
        0,
        "",
        "",
        False,
        {"pc": 0x202, "cycles": 4},
        True,
        [],
        "trace verification failed",
    )
    assert not failed.success


def test_describe_failure_combines_trace_and_golden_errors() -> None:
    reason = _describe_failure(
        exit_code=0,
        timed_out=False,
        timeout=1.0,
        stderr="",
        final_state={"pc": 0x202, "cycles": 1, "v": [0] * 16},
        expect={"pc": 0x200},
        state_match=False,
        trace_error="trace verification failed: bad hash",
    )
    assert reason is not None
    assert "trace verification failed" in reason
    assert "golden mismatch" in reason


def test_validate_rom_reports_trace_verification_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    rom = tmp_path / "tiny.ch8"
    rom.write_bytes(bytes.fromhex("6001 1200"))
    trace = tmp_path / "bad.trace"
    trace.write_text("invalid\n", encoding="utf-8")

    def fake_run(command: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(str(command), 0, '{"pc": 514, "cycles": 2}\n', "")

    monkeypatch.setattr("chip8.runner.subprocess.run", fake_run)
    report = validate_rom(rom, cycles=2, trace=trace)
    assert not report.success
    assert report.failure_reason is not None
    assert "trace verification failed" in report.failure_reason
