"""Unit tests for the Disasm module."""

from chip8.disasm import Instruction, disassemble, format_disassembly
from chip8.opcode import decode


def test_instruction_format() -> None:
    instruction = Instruction(0x200, decode(0x6001))
    assert instruction.format() == "200: 6001  LD V0, 0x01"


def test_disassemble_at_custom_start() -> None:
    rom = bytes.fromhex("6001 1200")
    instructions = disassemble(rom, start=0x300)
    assert len(instructions) == 2
    assert instructions[0].address == 0x300
    assert instructions[1].address == 0x302


def test_disassemble_single_two_byte_rom() -> None:
    instructions = disassemble(bytes.fromhex("6001"))
    assert len(instructions) == 1
    assert instructions[0].address == 0x200


def test_disassemble_one_byte_rom_has_no_instructions() -> None:
    assert disassemble(b"\x60") == []


def test_format_disassembly_odd_trailing_byte() -> None:
    text = format_disassembly(b"\x60\x01\xab", start=0x400)
    assert "400: 6001  LD V0, 0x01" in text
    assert "402: AB    .byte 0xAB" in text


def test_format_disassembly_even_rom() -> None:
    text = format_disassembly(bytes.fromhex("6001 1200"))
    assert ".byte" not in text
    assert text.count("\n") == 1
