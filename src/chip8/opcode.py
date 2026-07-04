"""Opcode model: nibble-field extraction, dispatch helpers, and mnemonics.

Field semantics and mnemonic rules are documented in docs/output-formats.md.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Opcode:
    value: int

    @property
    def high(self) -> int:
        return (self.value >> 12) & 0xF

    @property
    def x(self) -> int:
        return (self.value >> 8) & 0xF

    @property
    def y(self) -> int:
        return (self.value >> 4) & 0xF

    @property
    def n(self) -> int:
        return self.value & 0xF

    @property
    def nn(self) -> int:
        return self.value & 0xFF

    @property
    def nnn(self) -> int:
        return self.value & 0xFFF

    @property
    def is_known(self) -> bool:
        value = self.value
        if value in (0x00E0, 0x00EE):
            return True
        if self.high in (0x1, 0x2, 0x3, 0x4, 0x6, 0x7, 0xA, 0xB, 0xC, 0xD):
            return True
        if self.high in (0x5, 0x9):
            return self.n == 0
        if self.high == 0x8:
            return self.n in (0, 1, 2, 3, 4, 5, 6, 7, 0xE)
        if self.high == 0xE:
            return self.nn in (0x9E, 0xA1)
        if self.high == 0xF:
            return self.nn in (0x07, 0x0A, 0x15, 0x18, 0x1E, 0x29, 0x33, 0x55, 0x65)
        return False

    def mnemonic(self) -> str:
        x, y, n, nn, nnn = self.x, self.y, self.n, self.nn, self.nnn
        exact = {0x00E0: "CLS", 0x00EE: "RET"}
        if self.value in exact:
            return exact[self.value]
        formats = {
            0x1: f"JP 0x{nnn:03X}",
            0x2: f"CALL 0x{nnn:03X}",
            0x3: f"SE V{x:X}, 0x{nn:02X}",
            0x4: f"SNE V{x:X}, 0x{nn:02X}",
            0x6: f"LD V{x:X}, 0x{nn:02X}",
            0x7: f"ADD V{x:X}, 0x{nn:02X}",
            0xA: f"LD I, 0x{nnn:03X}",
            0xB: f"JP V0, 0x{nnn:03X}",
            0xC: f"RND V{x:X}, 0x{nn:02X}",
            0xD: f"DRW V{x:X}, V{y:X}, 0x{n:X}",
        }
        if self.high in formats:
            return formats[self.high]
        if self.high == 0x5 and n == 0:
            return f"SE V{x:X}, V{y:X}"
        if self.high == 0x9 and n == 0:
            return f"SNE V{x:X}, V{y:X}"
        if self.high == 0x8:
            operations = {
                0: "LD", 1: "OR", 2: "AND", 3: "XOR", 4: "ADD",
                5: "SUB", 6: "SHR", 7: "SUBN", 0xE: "SHL",
            }
            if n in operations:
                return f"{operations[n]} V{x:X}, V{y:X}"
        if self.high == 0xE:
            return {0x9E: f"SKP V{x:X}", 0xA1: f"SKNP V{x:X}"}.get(nn, self.unknown())
        if self.high == 0xF:
            operations = {
                0x07: f"LD V{x:X}, DT",
                0x0A: f"LD V{x:X}, K",
                0x15: f"LD DT, V{x:X}",
                0x18: f"LD ST, V{x:X}",
                0x1E: f"ADD I, V{x:X}",
                0x29: f"LD F, V{x:X}",
                0x33: f"LD B, V{x:X}",
                0x55: f"LD [I], V{x:X}",
                0x65: f"LD V{x:X}, [I]",
            }
            return operations.get(nn, self.unknown())
        return self.unknown()

    def unknown(self) -> str:
        return f".word 0x{self.value:04X}"


def decode(value: int) -> Opcode:
    return Opcode(value & 0xFFFF)

