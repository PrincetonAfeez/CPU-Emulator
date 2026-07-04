"""Hash-chained, tamper-evident execution traces using SHA-256."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import TextIO

from .errors import TraceVerificationError

TRACE_FORMAT = "chip8-trace-v2"
ZERO_HASH = "0" * 64

REQUIRED_RECORD_FIELDS = frozenset(
    {
        "sequence",
        "pc",
        "opcode",
        "before_pc",
        "after_pc",
        "cycles",
        "v",
        "i",
        "delay_timer",
        "sound_timer",
        "stack",
        "awaiting_key",
        "previous_hash",
    }
)

REQUIRED_SNAPSHOT_FIELDS = frozenset(
    {
        "pc",
        "i",
        "v",
        "stack",
        "delay_timer",
        "sound_timer",
        "cycles",
        "awaiting_key",
    }
)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _canonical(data: dict[str, object]) -> bytes:
    return json.dumps(data, sort_keys=True, separators=(",", ":")).encode()


def _require_snapshot(snapshot: dict[str, object], label: str) -> None:
    missing = REQUIRED_SNAPSHOT_FIELDS - snapshot.keys()
    if missing:
        missing_text = ", ".join(sorted(missing))
        raise TraceVerificationError(f"{label} snapshot missing fields: {missing_text}")


def _validate_record_schema(record: dict[str, object], line_number: int) -> None:
    missing = REQUIRED_RECORD_FIELDS - record.keys()
    if missing:
        missing_text = ", ".join(sorted(missing))
        raise TraceVerificationError(
            f"line {line_number} is missing required trace fields: {missing_text}"
        )


def _validate_record_types(record: dict[str, object], line_number: int) -> None:
    int_fields = (
        "sequence",
        "pc",
        "opcode",
        "before_pc",
        "after_pc",
        "cycles",
        "i",
        "delay_timer",
        "sound_timer",
    )
    for field_name in int_fields:
        if not isinstance(record.get(field_name), int):
            raise TraceVerificationError(
                f"line {line_number} field {field_name!r} must be an integer"
            )
    if not isinstance(record.get("awaiting_key"), bool):
        raise TraceVerificationError(
            f"line {line_number} field 'awaiting_key' must be a boolean"
        )
    registers = record.get("v")
    if (
        not isinstance(registers, list)
        or len(registers) != 16
        or not all(isinstance(value, int) for value in registers)
    ):
        raise TraceVerificationError(
            f"line {line_number} field 'v' must be a list of 16 integers"
        )
    stack = record.get("stack")
    if not isinstance(stack, list) or not all(isinstance(value, int) for value in stack):
        raise TraceVerificationError(
            f"line {line_number} field 'stack' must be a list of integers"
        )


@dataclass(slots=True)
class TraceWriter:
    stream: TextIO
    previous_hash: str = field(default=ZERO_HASH)
    sequence: int = 0

    @classmethod
    def open(cls, path: Path, *, rom: bytes, quirks: dict[str, object]) -> TraceWriter:
        path.parent.mkdir(parents=True, exist_ok=True)
        stream = path.open("w", encoding="utf-8", newline="\n")
        header: dict[str, object] = {
            "format": TRACE_FORMAT,
            "rom_sha256": sha256_bytes(rom),
            "quirks": quirks,
        }
        stream.write(json.dumps(header, sort_keys=True) + "\n")
        # Seed the chain with the header hash so the ROM identity and quirks are
        # tamper-evident too, not just the per-instruction records.
        genesis = hashlib.sha256(_canonical(header)).hexdigest()
        return cls(stream, previous_hash=genesis)

    def record(
        self,
        pc: int,
        opcode: int,
        before: dict[str, object],
        after: dict[str, object],
    ) -> None:
        _require_snapshot(before, "before")
        _require_snapshot(after, "after")
        payload: dict[str, object] = {
            "sequence": self.sequence,
            "pc": pc,
            "opcode": opcode,
            "before_pc": before["pc"],
            "after_pc": after["pc"],
            "cycles": after["cycles"],
            "v": after["v"],
            "i": after["i"],
            "delay_timer": after["delay_timer"],
            "sound_timer": after["sound_timer"],
            "stack": after["stack"],
            "awaiting_key": after["awaiting_key"],
            "previous_hash": self.previous_hash,
        }
        digest = hashlib.sha256(_canonical(payload)).hexdigest()
        record = {**payload, "hash": digest}
        self.stream.write(json.dumps(record, sort_keys=True) + "\n")
        self.stream.flush()
        self.previous_hash = digest
        self.sequence += 1

    def close(self) -> None:
        self.stream.close()

    def __enter__(self) -> TraceWriter:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()


def read_header(path: Path) -> dict[str, object]:
    """Return the parsed first-line header (format, rom_sha256, quirks)."""
    with path.open(encoding="utf-8") as stream:
        line = stream.readline()
    try:
        header = json.loads(line)
    except json.JSONDecodeError as exc:
        raise TraceVerificationError("trace header is not valid JSON") from exc
    if not isinstance(header, dict):
        raise TraceVerificationError("trace header is not a JSON object")
    return header


def verify_trace(path: Path) -> tuple[int, str]:
    with path.open(encoding="utf-8") as stream:
        try:
            header = json.loads(stream.readline())
        except json.JSONDecodeError as exc:
            raise TraceVerificationError("trace header is not valid JSON") from exc
        recorded_format = header.get("format")
        if recorded_format != TRACE_FORMAT:
            if recorded_format == "chip8-trace-v1":
                raise TraceVerificationError(
                    "trace format chip8-trace-v1 is no longer supported; "
                    "re-record with chip8-trace-v2"
                )
            raise TraceVerificationError("unsupported or missing trace format")
        # Recompute the genesis link from the header; any edit to the recorded
        # ROM hash or quirks breaks the first record's chain.
        previous = hashlib.sha256(_canonical(header)).hexdigest()
        count = 0
        for line_number, line in enumerate(stream, start=2):
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError as exc:
                raise TraceVerificationError(f"line {line_number} is not valid JSON") from exc
            actual_hash = record.pop("hash", None)
            _validate_record_schema(record, line_number)
            _validate_record_types(record, line_number)
            if record.get("previous_hash") != previous:
                raise TraceVerificationError(f"hash-chain link is broken at line {line_number}")
            expected_hash = hashlib.sha256(_canonical(record)).hexdigest()
            if actual_hash != expected_hash:
                raise TraceVerificationError(f"record hash mismatch at line {line_number}")
            if record.get("sequence") != count:
                raise TraceVerificationError(f"sequence mismatch at line {line_number}")
            previous = expected_hash
            count += 1
        if count == 0:
            raise TraceVerificationError("trace contains a header but no execution records")
    return count, previous
