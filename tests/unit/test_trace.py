"""Unit tests for the Trace module."""

import hashlib
import json
from collections.abc import Callable
from pathlib import Path
from typing import cast

import pytest

from chip8.errors import TraceVerificationError
from chip8.quirks import get_quirks
from chip8.trace import (
    TRACE_FORMAT,
    TraceWriter,
    _canonical,
    read_header,
    sha256_bytes,
    verify_trace,
)


def _modern_quirks() -> dict[str, object]:
    return get_quirks("modern").describe()


def _mutate_trace_record(
    tmp_path: Path, mutate: Callable[[dict[str, object]], None]
) -> Path:
    path = tmp_path / "trace.log"
    writer = TraceWriter.open(path, rom=b"\x60\x01", quirks=_modern_quirks())
    writer.record(
        0x200,
        0x6001,
        _trace_state(pc=0x200, cycles=0),
        _trace_state(v=[1] + [0] * 15),
    )
    writer.close()
    record = json.loads(path.read_text(encoding="utf-8").splitlines()[1])
    mutate(record)
    lines = path.read_text(encoding="utf-8").splitlines()
    lines[1] = json.dumps(record)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _valid_header(**overrides: object) -> dict[str, object]:
    header: dict[str, object] = {
        "format": TRACE_FORMAT,
        "rom_sha256": sha256_bytes(b"\x60\x01"),
        "quirks": _modern_quirks(),
    }
    header.update(overrides)
    return header


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
    with TraceWriter.open(path, rom=b"\x60\x01", quirks=_modern_quirks()) as writer:
        writer.record(0x200, 0x6001, before, after)
    assert verify_trace(path)[0] == 1


def test_read_header_parses_first_line(tmp_path: Path) -> None:
    path = tmp_path / "trace.log"
    TraceWriter.open(path, rom=b"\x60\x01", quirks=_modern_quirks()).close()
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


@pytest.mark.parametrize(
    "header_json",
    [
        "[]",
        "null",
        '"text"',
    ],
)
def test_verify_rejects_non_object_header(tmp_path: Path, header_json: str) -> None:
    path = tmp_path / "trace.log"
    path.write_text(header_json + "\n", encoding="utf-8")
    with pytest.raises(TraceVerificationError, match="trace header is not a JSON object"):
        verify_trace(path)


def test_verify_rejects_unsupported_format(tmp_path: Path) -> None:
    path = tmp_path / "trace.log"
    path.write_text(
        json.dumps(_valid_header(format="chip8-trace-v9")) + "\n",
        encoding="utf-8",
    )
    with pytest.raises(TraceVerificationError, match="unsupported or missing"):
        verify_trace(path)


@pytest.mark.parametrize(
    "mutate,message",
    [
        (lambda header: header.pop("rom_sha256"), "missing fields: rom_sha256"),
        (lambda header: header.pop("quirks"), "missing fields: quirks"),
        (lambda header: header.__setitem__("rom_sha256", 123), "rom_sha256"),
        (lambda header: header.__setitem__("rom_sha256", "0" * 63), "rom_sha256"),
        (lambda header: header.__setitem__("rom_sha256", "GG" + "0" * 62), "rom_sha256"),
        (lambda header: header.__setitem__("quirks", []), "quirks"),
        (
            lambda header: header.__setitem__(
                "quirks",
                {
                    "name": "modern",
                    "shift_uses_vy": False,
                    "load_store_increment_i": False,
                    "draw_wrap": False,
                },
            ),
            "quirks missing fields",
        ),
        (
            lambda header: header.__setitem__("quirks", {**_modern_quirks(), "extra": True}),
            "quirks has unknown fields",
        ),
        (
            lambda header: cast(dict[str, object], header["quirks"]).__setitem__(
                "shift_uses_vy", "yes"
            ),
            "shift_uses_vy",
        ),
        (
            lambda header: cast(dict[str, object], header["quirks"]).__setitem__(
                "name", "superchip"
            ),
            'name\' must be "classic" or "modern"',
        ),
    ],
)
def test_verify_rejects_invalid_header_schema(
    tmp_path: Path, mutate: Callable[[dict[str, object]], None], message: str
) -> None:
    header = _valid_header()
    mutate(header)
    path = tmp_path / "trace.log"
    path.write_text(json.dumps(header, sort_keys=True) + "\n", encoding="utf-8")
    with pytest.raises(TraceVerificationError, match=message):
        verify_trace(path)


@pytest.mark.parametrize(
    "bad_name",
    [
        [],
        {},
        None,
        True,
        123,
        "superchip",
    ],
)
def test_verify_rejects_invalid_quirk_name(
    tmp_path: Path, bad_name: object
) -> None:
    header = _valid_header()
    cast(dict[str, object], header["quirks"])["name"] = bad_name
    path = tmp_path / "trace.log"
    path.write_text(json.dumps(header, sort_keys=True) + "\n", encoding="utf-8")
    with pytest.raises(
        TraceVerificationError,
        match='name\' must be "classic" or "modern"',
    ):
        verify_trace(path)


def test_trace_verify_invalid_quirk_name_exits_1_not_70(tmp_path: Path) -> None:
    from chip8.cli import main

    header = _valid_header()
    cast(dict[str, object], header["quirks"])["name"] = []
    trace = tmp_path / "trace.log"
    trace.write_text(json.dumps(header, sort_keys=True) + "\n", encoding="utf-8")
    assert main(["trace-verify", str(trace)]) == 1


@pytest.mark.parametrize(
    "record_json,message",
    [
        ("[]", "line 2 trace record is not a JSON object"),
        ("null", "line 2 trace record is not a JSON object"),
        ('"text"', "line 2 trace record is not a JSON object"),
    ],
)
def test_verify_rejects_non_object_record(
    tmp_path: Path, record_json: str, message: str
) -> None:
    path = tmp_path / "trace.log"
    writer = TraceWriter.open(path, rom=b"\x60\x01", quirks=_modern_quirks())
    writer.record(0x200, 0x6001, _trace_state(pc=0x200, cycles=0), _trace_state(v=[1] + [0] * 15))
    writer.close()
    lines = path.read_text(encoding="utf-8").splitlines()
    lines[1] = record_json
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    with pytest.raises(TraceVerificationError, match=message):
        verify_trace(path)


def test_verify_rejects_invalid_record_json(tmp_path: Path) -> None:
    path = tmp_path / "trace.log"
    writer = TraceWriter.open(path, rom=b"\x60\x01", quirks=_modern_quirks())
    writer.record(0x200, 0x6001, _trace_state(pc=0x200, cycles=0), _trace_state(v=[1] + [0] * 15))
    writer.close()
    lines = path.read_text(encoding="utf-8").splitlines()
    lines[1] = "not-json"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    with pytest.raises(TraceVerificationError, match="not valid JSON"):
        verify_trace(path)


def test_verify_rejects_broken_hash_chain(tmp_path: Path) -> None:
    path = tmp_path / "trace.log"
    writer = TraceWriter.open(path, rom=b"\x60\x01", quirks=_modern_quirks())
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
    writer = TraceWriter.open(path, rom=b"\x60\x01", quirks=_modern_quirks())
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
    writer = TraceWriter.open(path, rom=b"\x60\x01", quirks=_modern_quirks())
    writer.record(0x200, 0x6001, _trace_state(pc=0x200, cycles=0), _trace_state(v=[1] + [0] * 15))
    writer.close()
    lines = path.read_text(encoding="utf-8").splitlines()
    record = json.loads(lines[1])
    record[field] = bad_value
    lines[1] = json.dumps(record)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    with pytest.raises(TraceVerificationError, match=message):
        verify_trace(path)


@pytest.mark.parametrize(
    "mutate,message",
    [
        (lambda record: record.__setitem__("pc", True), "field 'pc'"),
        (lambda record: record.__setitem__("sequence", False), "field 'sequence'"),
        (
            lambda record: record.__setitem__("v", [True] + [0] * 15),
            "field 'v'",
        ),
        (lambda record: record.__setitem__("stack", [False]), "field 'stack'"),
        (lambda record: record.__setitem__("pc", -1), "field 'pc'"),
        (lambda record: record.__setitem__("pc", 0x1000), "field 'pc'"),
        (lambda record: record.__setitem__("opcode", 0x10000), "field 'opcode'"),
        (lambda record: record.__setitem__("delay_timer", 256), "field 'delay_timer'"),
        (
            lambda record: record.__setitem__("v", [256] + [0] * 15),
            "field 'v' entries",
        ),
        (lambda record: record.__setitem__("stack", [0x1000]), "field 'stack' entries"),
        (lambda record: record.__setitem__("previous_hash", "0" * 63), "previous_hash"),
        (
            lambda record: record.__setitem__("previous_hash", "GG" + "0" * 62),
            "previous_hash",
        ),
        (lambda record: record.__setitem__("hash", "0" * 63), "field 'hash'"),
        (lambda record: record.__setitem__("hash", "GG" + "0" * 62), "field 'hash'"),
    ],
)
def test_verify_rejects_invalid_record_schema_values(
    tmp_path: Path, mutate: Callable[[dict[str, object]], None], message: str
) -> None:
    path = _mutate_trace_record(tmp_path, mutate)
    with pytest.raises(TraceVerificationError, match=message):
        verify_trace(path)


def test_record_rejects_incomplete_before_snapshot(tmp_path: Path) -> None:
    path = tmp_path / "trace.log"
    writer = TraceWriter.open(path, rom=b"\x60\x01", quirks=_modern_quirks())
    with pytest.raises(TraceVerificationError, match="before snapshot missing"):
        writer.record(0x200, 0x6001, {"pc": 0x200}, _trace_state())
    writer.close()
