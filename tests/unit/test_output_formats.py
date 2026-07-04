"""Contract tests for documented disassembly and CFG output structures."""

from __future__ import annotations

import dataclasses

from chip8.cfg import CFG, build_cfg
from chip8.disasm import Instruction, disassemble, format_disassembly
from chip8.opcode import Opcode, decode


def test_instruction_documents_stable_fields() -> None:
    fields = {field.name for field in dataclasses.fields(Instruction)}
    assert fields == {"address", "opcode"}


def test_disassemble_orders_instructions_by_ascending_address() -> None:
    rom = bytes.fromhex("6001 7001 1202")
    addresses = [instruction.address for instruction in disassemble(rom)]
    assert addresses == [0x200, 0x202, 0x204]


def test_disassemble_omits_odd_trailing_byte_from_instruction_list() -> None:
    rom = b"\x60\x01\xab"
    instructions = disassemble(rom)
    assert len(instructions) == 1
    assert instructions[0].address == 0x200
    assert format_disassembly(rom).endswith("202: AB    .byte 0xAB")


def test_opcode_documents_stable_fields_and_derivations() -> None:
    opcode = Opcode(0xDAB5)
    assert opcode.value == 0xDAB5
    assert opcode.high == 0xD
    assert opcode.x == 0xA
    assert opcode.y == 0xB
    assert opcode.n == 0x5
    assert opcode.nn == 0xB5
    assert opcode.nnn == 0xAB5


def test_opcode_mnemonic_known_vs_unknown() -> None:
    known = decode(0x6001)
    unknown = decode(0x0000)
    assert known.is_known
    assert known.mnemonic() == "LD V0, 0x01"
    assert not unknown.is_known
    assert unknown.mnemonic() == unknown.unknown() == ".word 0x0000"


def test_cfg_documents_stable_fields() -> None:
    fields = {field.name for field in dataclasses.fields(CFG)}
    assert fields == {
        "nodes",
        "edges",
        "unresolved",
        "jump_targets",
        "call_targets",
        "malformed",
    }


def test_cfg_field_meanings_on_sample_rom() -> None:
    graph = build_cfg(bytes.fromhex("1206 0000 B300 00EE"))
    assert isinstance(graph.nodes[0x200].opcode, Opcode)
    assert 0x206 in graph.edges[0x200]
    assert graph.jump_targets == {0x206}
    assert 0x202 in graph.malformed
    assert graph.unresolved[0x204] == "dynamic BNNN jump"
    assert graph.reachable(start=0x200) == {0x200, 0x206}
