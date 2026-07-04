"""Unit tests for the Opcode module."""

import pytest

from chip8.opcode import Opcode, decode

KNOWN_OPCODES = [
    (0x00E0, "CLS"),
    (0x00EE, "RET"),
    (0x1200, "JP 0x200"),
    (0x2206, "CALL 0x206"),
    (0x3107, "SE V1, 0x07"),
    (0x4108, "SNE V1, 0x08"),
    (0x5100, "SE V1, V0"),
    (0x6001, "LD V0, 0x01"),
    (0x7001, "ADD V0, 0x01"),
    (0x8100, "LD V1, V0"),
    (0x8121, "OR V1, V2"),
    (0x8122, "AND V1, V2"),
    (0x8123, "XOR V1, V2"),
    (0x8124, "ADD V1, V2"),
    (0x8125, "SUB V1, V2"),
    (0x8126, "SHR V1, V2"),
    (0x8127, "SUBN V1, V2"),
    (0x812E, "SHL V1, V2"),
    (0x9100, "SNE V1, V0"),
    (0xA300, "LD I, 0x300"),
    (0xB200, "JP V0, 0x200"),
    (0xC0FF, "RND V0, 0xFF"),
    (0xD015, "DRW V0, V1, 0x5"),
    (0xE09E, "SKP V0"),
    (0xE0A1, "SKNP V0"),
    (0xF007, "LD V0, DT"),
    (0xF00A, "LD V0, K"),
    (0xF015, "LD DT, V0"),
    (0xF018, "LD ST, V0"),
    (0xF01E, "ADD I, V0"),
    (0xF029, "LD F, V0"),
    (0xF033, "LD B, V0"),
    (0xF055, "LD [I], V0"),
    (0xF065, "LD V0, [I]"),
]

UNKNOWN_OPCODES = [
    0x0000,
    0x5123,
    0x9123,
    0x8128,
    0xE19F,
    0xF199,
]


@pytest.mark.parametrize("value,mnemonic", KNOWN_OPCODES)
def test_known_opcode_is_recognized_and_named(value: int, mnemonic: str) -> None:
    opcode = decode(value)
    assert opcode.is_known
    assert opcode.mnemonic() == mnemonic


@pytest.mark.parametrize("value", UNKNOWN_OPCODES)
def test_unknown_opcode_is_not_known(value: int) -> None:
    opcode = decode(value)
    assert not opcode.is_known
    assert opcode.mnemonic().startswith(".word")


def test_decode_masks_to_sixteen_bits() -> None:
    opcode = decode(0x1_6001)
    assert opcode.value == 0x6001


def test_opcode_nibble_fields() -> None:
    opcode = Opcode(0xDAB5)
    assert opcode.high == 0xD
    assert opcode.x == 0xA
    assert opcode.y == 0xB
    assert opcode.n == 0x5
    assert opcode.nn == 0xB5
    assert opcode.nnn == 0xAB5


def test_unknown_method() -> None:
    assert decode(0x0000).unknown() == ".word 0x0000"
