"""Unit tests for the Errors module."""

import pytest

from chip8.errors import (
    Chip8Error,
    InputUnavailableError,
    InvalidKeyError,
    InvalidOpcodeError,
    MemoryAccessError,
    RomLoadError,
    StackOverflowError,
    StackUnderflowError,
    TraceVerificationError,
)


@pytest.mark.parametrize(
    "error_type",
    [
        MemoryAccessError,
        RomLoadError,
        StackOverflowError,
        StackUnderflowError,
        TraceVerificationError,
        InputUnavailableError,
        InvalidKeyError,
    ],
)
def test_error_types_inherit_chip8_error(error_type: type[Exception]) -> None:
    assert issubclass(error_type, Chip8Error)


def test_invalid_opcode_error_carries_context() -> None:
    error = InvalidOpcodeError(0xFFFF, 0x200)
    assert error.opcode == 0xFFFF
    assert error.address == 0x200
    assert "0xFFFF" in str(error)
    assert "0x200" in str(error)
