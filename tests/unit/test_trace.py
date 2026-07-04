"""Unit tests for the Trace module."""

import hashlib
import json
from pathlib import Path

import pytest

from chip8.errors import TraceVerificationError
from chip8.trace import (
    TRACE_FORMAT,
    TraceWriter,
    _canonical,
    read_header,
    sha256_bytes,
    verify_trace,
)


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


def test_sha256_bytes_is_deterministic() -> None:
    digest = sha256_bytes(b"\x60\x01")
    assert len(digest) == 64
    assert digest == sha256_bytes(b"\x60\x01")
    assert digest != sha256_bytes(b"\x60\x02")


def test_trace_writer_context_manager(tmp_path: Path) -> None:
    path = tmp_path / "trace.log"
    before = _trace_state(pc=0x200, cycles=0)
    after = _trace_state(v=[1] + [0] * 15)
    with TraceWriter.open(path, rom=b"\x60\x01", quirks={"name": "modern"}) as writer:
        writer.record(0x200, 0x6001, before, after)
    assert verify_trace(path)[0] == 1


def test_read_header_parses_first_line(tmp_path: Path) -> None:
    path = tmp_path / "trace.log"
    TraceWriter.open(path, rom=b"\x60\x01", quirks={"name": "modern"}).close()
    header = read_header(path)
    assert header["format"] == TRACE_FORMAT
    assert "rom_sha256" in header


def test_read_header_rejects_invalid_json(tmp_path: Path) -> None:
    path = tmp_path / "bad.log"
    path.write_text("not json\n", encoding="utf-8")
    with pytest.raises(TraceVerificationError, match="not valid JSON"):
        read_header(path)


def test_read_header_rejects_non_object(tmp_path: Path) -> None:
    path = tmp_path / "bad.log"
    path.write_text("[1, 2]\n", encoding="utf-8")
    with pytest.raises(TraceVerificationError, match="not a JSON object"):
        read_header(path)


def test_verify_rejects_unsupported_format(tmp_path: Path) -> None:
    path = tmp_path / "trace.log"
    path.write_text(
        json.dumps({"format": "chip8-trace-v9", "rom_sha256": "00" * 32, "quirks": {}})
        + "\n",
        encoding="utf-8",
    )
    with pytest.raises(TraceVerificationError, match="unsupported or missing"):
        verify_trace(path)


def test_verify_rejects_invalid_record_json(tmp_path: Path) -> None:
    path = tmp_path / "trace.log"
    writer = TraceWriter.open(path, rom=b"\x60\x01", quirks={"name": "modern"})
    writer.record(0x200, 0x6001, _trace_state(pc=0x200, cycles=0), _trace_state(v=[1] + [0] * 15))
    writer.close()
    lines = path.read_text(encoding="utf-8").splitlines()
    lines[1] = "not-json"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    with pytest.raises(TraceVerificationError, match="not valid JSON"):
        verify_trace(path)


def test_verify_rejects_broken_hash_chain(tmp_path: Path) -> None:
    path = tmp_path / "trace.log"
    writer = TraceWriter.open(path, rom=b"\x60\x01", quirks={"name": "modern"})
    writer.record(0x200, 0x6001, _trace_state(pc=0x200, cycles=0), _trace_state(v=[1] + [0] * 15))
    writer.close()
    lines = path.read_text(encoding="utf-8").splitlines()
    record = json.loads(lines[1])
    record["previous_hash"] = "0" * 64
    lines[1] = json.dumps(record)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    with pytest.raises(TraceVerificationError, match="hash-chain link is broken"):
        verify_trace(path)


def test_verify_rejects_sequence_mismatch(tmp_path: Path) -> None:
    path = tmp_path / "trace.log"
    writer = TraceWriter.open(path, rom=b"\x60\x01", quirks={"name": "modern"})
    writer.record(0x200, 0x6001, _trace_state(pc=0x200, cycles=0), _trace_state(v=[1] + [0] * 15))
    writer.close()
    lines = path.read_text(encoding="utf-8").splitlines()
    record = json.loads(lines[1])
    record["sequence"] = 9
    record.pop("hash", None)
    record["hash"] = hashlib.sha256(_canonical(record)).hexdigest()
    lines[1] = json.dumps(record)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    with pytest.raises(TraceVerificationError, match="sequence mismatch"):
        verify_trace(path)


@pytest.mark.parametrize(
    "field,bad_value,message",
    [
        ("pc", "x", "field 'pc'"),
        ("awaiting_key", 1, "field 'awaiting_key'"),
        ("v", [0] * 15, "field 'v'"),
        ("stack", ["bad"], "field 'stack'"),
    ],
)
def test_verify_rejects_invalid_field_types(
    tmp_path: Path, field: str, bad_value: object, message: str
) -> None:
    path = tmp_path / "trace.log"
    writer = TraceWriter.open(path, rom=b"\x60\x01", quirks={"name": "modern"})
    writer.record(0x200, 0x6001, _trace_state(pc=0x200, cycles=0), _trace_state(v=[1] + [0] * 15))
    writer.close()
    lines = path.read_text(encoding="utf-8").splitlines()
    record = json.loads(lines[1])
    record[field] = bad_value
    lines[1] = json.dumps(record)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    with pytest.raises(TraceVerificationError, match=message):
        verify_trace(path)


def test_record_rejects_incomplete_before_snapshot(tmp_path: Path) -> None:
    path = tmp_path / "trace.log"
    writer = TraceWriter.open(path, rom=b"\x60\x01", quirks={"name": "modern"})
    with pytest.raises(TraceVerificationError, match="before snapshot missing"):
        writer.record(0x200, 0x6001, {"pc": 0x200}, _trace_state())
    writer.close()
