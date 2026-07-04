"""Hash-chained, tamper-evident execution traces using SHA-256."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import TextIO

from .errors import TraceVerificationError
from .quirks import PROFILES

TRACE_FORMAT = "chip8-trace-v2"
ZERO_HASH = "0" * 64
_HEX_DIGITS = frozenset("0123456789abcdef")

REQUIRED_HEADER_FIELDS = frozenset({"format", "rom_sha256", "quirks"})
REQUIRED_QUIRK_FIELDS = frozenset(PROFILES["modern"].describe().keys())
SUPPORTED_QUIRK_NAMES = frozenset(PROFILES.keys())

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

ADDRESS_MAX = 0xFFF
OPCODE_MAX = 0xFFFF
BYTE_MAX = 0xFF


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _canonical(data: dict[str, object]) -> bytes:
    return json.dumps(data, sort_keys=True, separators=(",", ":")).encode()


def _is_json_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _require_int_field(
    record: dict[str, object],
    field_name: str,
    line_number: int,
    *,
    minimum: int,
    maximum: int | None = None,
) -> int:
    value = record.get(field_name)
    if not _is_json_int(value):
        raise TraceVerificationError(
            f"line {line_number} field {field_name!r} must be an integer"
        )
    assert isinstance(value, int)
    if value < minimum or (maximum is not None and value > maximum):
        if maximum is not None:
            raise TraceVerificationError(
                f"line {line_number} field {field_name!r} must be between "
                f"{minimum} and {maximum}"
            )
        raise TraceVerificationError(
            f"line {line_number} field {field_name!r} must be >= {minimum}"
        )
    return value


def _require_hex_digest(value: object, field_name: str, line_number: int) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(char not in _HEX_DIGITS for char in value)
    ):
        raise TraceVerificationError(
            f"line {line_number} field {field_name!r} must be a 64-character lowercase hex string"
        )
    return value


def _require_snapshot(snapshot: dict[str, object], label: str) -> None:
    missing = REQUIRED_SNAPSHOT_FIELDS - snapshot.keys()
    if missing:
        missing_text = ", ".join(sorted(missing))
        raise TraceVerificationError(f"{label} snapshot missing fields: {missing_text}")


def _validate_header_schema(header: dict[str, object]) -> None:
    missing = REQUIRED_HEADER_FIELDS - header.keys()
    if missing:
        missing_text = ", ".join(sorted(missing))
        raise TraceVerificationError(f"trace header missing fields: {missing_text}")
    recorded_format = header["format"]
    if recorded_format == "chip8-trace-v1":
        raise TraceVerificationError(
            "trace format chip8-trace-v1 is no longer supported; "
            "re-record with chip8-trace-v2"
        )
    if recorded_format != TRACE_FORMAT:
        raise TraceVerificationError("unsupported or missing trace format")
    digest = header["rom_sha256"]
    if (
        not isinstance(digest, str)
        or len(digest) != 64
        or any(char not in _HEX_DIGITS for char in digest)
    ):
        raise TraceVerificationError(
            "trace header field 'rom_sha256' must be a 64-character lowercase hex string"
        )
    quirks = header["quirks"]
    if not isinstance(quirks, dict):
        raise TraceVerificationError("trace header field 'quirks' must be a JSON object")
    missing_quirks = REQUIRED_QUIRK_FIELDS - quirks.keys()
    if missing_quirks:
        missing_text = ", ".join(sorted(missing_quirks))
        raise TraceVerificationError(f"trace header quirks missing fields: {missing_text}")
    unknown_quirks = quirks.keys() - REQUIRED_QUIRK_FIELDS
    if unknown_quirks:
        unknown_text = ", ".join(sorted(unknown_quirks))
        raise TraceVerificationError(f"trace header quirks has unknown fields: {unknown_text}")
    name = quirks["name"]
    if not isinstance(name, str) or name not in SUPPORTED_QUIRK_NAMES:
        raise TraceVerificationError(
            'trace header quirks field \'name\' must be "classic" or "modern"'
        )
    for field_name in REQUIRED_QUIRK_FIELDS - {"name"}:
        if not isinstance(quirks[field_name], bool):
            raise TraceVerificationError(
                f"trace header quirks field {field_name!r} must be a boolean"
            )


def _validate_record_schema(record: dict[str, object], line_number: int) -> None:
    missing = REQUIRED_RECORD_FIELDS - record.keys()
    if missing:
        missing_text = ", ".join(sorted(missing))
        raise TraceVerificationError(
            f"line {line_number} is missing required trace fields: {missing_text}"
        )


def _validate_record_types(record: dict[str, object], line_number: int) -> None:
    _require_int_field(record, "sequence", line_number, minimum=0)
    for field_name in ("pc", "before_pc", "after_pc", "i"):
        _require_int_field(record, field_name, line_number, minimum=0, maximum=ADDRESS_MAX)
    _require_int_field(record, "opcode", line_number, minimum=0, maximum=OPCODE_MAX)
    _require_int_field(record, "cycles", line_number, minimum=0)
    for field_name in ("delay_timer", "sound_timer"):
        _require_int_field(record, field_name, line_number, minimum=0, maximum=BYTE_MAX)
    if not isinstance(record.get("awaiting_key"), bool):
        raise TraceVerificationError(
            f"line {line_number} field 'awaiting_key' must be a boolean"
        )
    registers = record.get("v")
    if not isinstance(registers, list) or len(registers) != 16:
        raise TraceVerificationError(
            f"line {line_number} field 'v' must be a list of 16 integers"
        )
    for value in registers:
        if not _is_json_int(value):
            raise TraceVerificationError(
                f"line {line_number} field 'v' must be a list of 16 integers"
            )
        assert isinstance(value, int)
        if value < 0 or value > BYTE_MAX:
            raise TraceVerificationError(
                f"line {line_number} field 'v' entries must be between 0 and {BYTE_MAX}"
            )
    stack = record.get("stack")
    if not isinstance(stack, list):
        raise TraceVerificationError(
            f"line {line_number} field 'stack' must be a list of integers"
        )
    for value in stack:
        if not _is_json_int(value):
            raise TraceVerificationError(
                f"line {line_number} field 'stack' must be a list of integers"
            )
        assert isinstance(value, int)
        if value < 0 or value > ADDRESS_MAX:
            raise TraceVerificationError(
                f"line {line_number} field 'stack' entries must be between 0 and {ADDRESS_MAX}"
            )
    _require_hex_digest(record.get("previous_hash"), "previous_hash", line_number)


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
        _validate_header_schema(header)
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
        if not isinstance(header, dict):
            raise TraceVerificationError("trace header is not a JSON object")
        _validate_header_schema(header)
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
            if not isinstance(record, dict):
                raise TraceVerificationError(
                    f"line {line_number} trace record is not a JSON object"
                )
            actual_hash = record.pop("hash", None)
            _validate_record_schema(record, line_number)
            _validate_record_types(record, line_number)
            _require_hex_digest(actual_hash, "hash", line_number)
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
