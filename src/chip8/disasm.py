"""Linear-sweep disassembler producing addressed, readable mnemonics."""

from __future__ import annotations

from dataclasses import dataclass

from .memory import PROGRAM_START
from .opcode import Opcode, decode


@dataclass(frozen=True, slots=True)
class Instruction:
    address: int
    opcode: Opcode

    def format(self) -> str:
        return f"{self.address:03X}: {self.opcode.value:04X}  {self.opcode.mnemonic()}"


def disassemble(rom: bytes, start: int = PROGRAM_START) -> list[Instruction]:
    instructions = []
    for offset in range(0, len(rom) - 1, 2):
        value = (rom[offset] << 8) | rom[offset + 1]
        instructions.append(Instruction(start + offset, decode(value)))
    return instructions


def format_disassembly(rom: bytes, start: int = PROGRAM_START) -> str:
    lines = [instruction.format() for instruction in disassemble(rom, start)]
    if len(rom) % 2:
        lines.append(f"{start + len(rom) - 1:03X}: {rom[-1]:02X}    .byte 0x{rom[-1]:02X}")
    return "\n".join(lines)

