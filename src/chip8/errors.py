"""Errors that describe failures in terms of the emulated machine."""

from __future__ import annotations


class Chip8Error(Exception):
    """Base class for expected emulator failures."""


class MemoryAccessError(Chip8Error):
    pass


class RomLoadError(Chip8Error):
    pass


class InvalidOpcodeError(Chip8Error):
    def __init__(self, opcode: int, address: int) -> None:
        super().__init__(f"unsupported opcode 0x{opcode:04X} at 0x{address:03X}")
        self.opcode = opcode
        self.address = address


class StackOverflowError(Chip8Error):
    pass


class StackUnderflowError(Chip8Error):
    pass


class TraceVerificationError(Chip8Error):
    pass


class InputUnavailableError(Chip8Error):
    pass


class InvalidKeyError(Chip8Error):
    pass

