"""Process-controlled ROM validation runner: subprocess, capture, and report."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from collections.abc import Mapping
from dataclasses import asdict, dataclass, field
from pathlib import Path

from .errors import TraceVerificationError
from .trace import verify_trace


def _as_text(value: str | bytes | None) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode(errors="replace")
    return value


def _parse_final_state(stdout: str) -> dict[str, object] | None:
    """Extract the JSON CPU snapshot printed by a headless ``chip8 run``."""
    for line in reversed(stdout.splitlines()):
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            state = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(state, dict) and "pc" in state and "cycles" in state:
            return state
    return None


def _register_mismatch(
    key: str, expected: object, state: dict[str, object] | None
) -> str | None:
    if state is None:
        return f"{key}: expected {expected!r}, no snapshot available"
    if len(key) == 2 and key[0] == "v" and key[1] in "0123456789ABCDEFabcdef":
        index = int(key[1], 16)
        registers = state.get("v")
        actual: object = None
        if isinstance(registers, list) and len(registers) > index:
            actual = registers[index]
        if actual != expected:
            return f"V{index:X}: expected {expected}, got {actual}"
        return None
    actual = state.get(key)
    if key == "pc" and isinstance(expected, int) and isinstance(actual, int):
        if actual != expected:
            return f"pc: expected 0x{expected:03X}, got 0x{actual:03X}"
        return None
    if actual != expected:
        return f"{key}: expected {expected!r}, got {actual!r}"
    return None


def state_mismatches(
    state: dict[str, object] | None, expect: Mapping[str, object]
) -> list[str]:
    return [
        mismatch
        for key, expected in expect.items()
        if (mismatch := _register_mismatch(key, expected, state)) is not None
    ]


def _state_matches(state: dict[str, object] | None, expect: Mapping[str, object]) -> bool:
    return not state_mismatches(state, expect)


def _describe_failure(
    *,
    exit_code: int,
    timed_out: bool,
    timeout: float,
    stderr: str,
    final_state: dict[str, object] | None,
    expect: Mapping[str, object] | None,
    state_match: bool,
    trace_error: str | None,
) -> str | None:
    reasons: list[str] = []
    if trace_error is not None:
        reasons.append(trace_error)
    if timed_out:
        message = f"timed out after {timeout:.1f}s"
        if isinstance(final_state, dict) and final_state.get("awaiting_key"):
            message += (
                " (CPU blocked on FX0A key wait; headless mode does not poll keyboard input)"
            )
        reasons.append(message)
    elif exit_code != 0:
        detail = stderr.strip() or f"emulator exited with code {exit_code}"
        reasons.append(detail)
    elif final_state is None:
        reasons.append("no final CPU snapshot in stdout")
    if expect and not state_match:
        mismatches = state_mismatches(final_state, expect)
        if mismatches:
            reasons.append("golden mismatch: " + "; ".join(mismatches))
    return "; ".join(reasons) if reasons else None


@dataclass(frozen=True, slots=True)
class ValidationReport:
    command: list[str]
    exit_code: int
    stdout: str
    stderr: str
    timed_out: bool
    final_state: dict[str, object] | None = None
    state_match: bool = True
    mismatch_details: list[str] = field(default_factory=list)
    failure_reason: str | None = None

    @property
    def success(self) -> bool:
        return (
            self.exit_code == 0
            and not self.timed_out
            and self.final_state is not None
            and isinstance(self.final_state.get("cycles"), int)
            and self.state_match
            and self.failure_reason is None
        )

    def to_json(self) -> str:
        return json.dumps({**asdict(self), "success": self.success}, indent=2)


def _verify_trace_file(trace: Path) -> str | None:
    try:
        verify_trace(trace)
    except TraceVerificationError as exc:
        return f"trace verification failed: {exc}"
    return None


def validate_rom(
    rom: Path,
    *,
    cycles: int = 500,
    timeout: float = 10.0,
    quirks: str = "modern",
    trace: Path | None = None,
    expect: Mapping[str, object] | None = None,
) -> ValidationReport:
    command = [
        sys.executable,
        "-m",
        "chip8",
        "run",
        str(rom),
        "--headless",
        "--cycles",
        str(cycles),
        "--seed",
        "0",
        "--quirks",
        quirks,
    ]
    if trace is not None:
        command.extend(("--trace", str(trace)))
    # Make the child import chip8 even when run from a source checkout without
    # an editable install, by putting this package's src root on PYTHONPATH.
    env = dict(os.environ)
    package_root = str(Path(__file__).resolve().parents[1])
    existing = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = os.pathsep.join(filter(None, (package_root, existing)))
    try:
        completed = subprocess.run(
            command,
            text=True,
            encoding="utf-8",
            capture_output=True,
            timeout=timeout,
            check=False,
            env=env,
        )
        final_state = _parse_final_state(completed.stdout)
        state_match = _state_matches(final_state, expect) if expect else True
        mismatch_details = state_mismatches(final_state, expect) if expect else []
        trace_error = _verify_trace_file(trace) if trace is not None and trace.is_file() else None
        failure_reason = _describe_failure(
            exit_code=completed.returncode,
            timed_out=False,
            timeout=timeout,
            stderr=completed.stderr,
            final_state=final_state,
            expect=expect,
            state_match=state_match and trace_error is None,
            trace_error=trace_error,
        )
        if trace_error is not None:
            state_match = False
        return ValidationReport(
            command,
            completed.returncode,
            completed.stdout,
            completed.stderr,
            False,
            final_state,
            state_match,
            mismatch_details,
            failure_reason,
        )
    except subprocess.TimeoutExpired as exc:
        stdout = _as_text(exc.stdout)
        final_state = _parse_final_state(stdout)
        state_match = not expect
        mismatch_details = state_mismatches(final_state, expect) if expect else []
        stderr = _as_text(exc.stderr) or f"validation timed out after {timeout:.1f}s"
        failure_reason = _describe_failure(
            exit_code=-1,
            timed_out=True,
            timeout=timeout,
            stderr=stderr,
            final_state=final_state,
            expect=expect,
            state_match=state_match,
            trace_error=None,
        )
        return ValidationReport(
            command,
            -1,
            stdout,
            stderr,
            True,
            final_state,
            state_match,
            mismatch_details,
            failure_reason,
        )
