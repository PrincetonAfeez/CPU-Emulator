"""Unit tests for the CPU module."""

import pytest

from chip8.cpu import CPU
from chip8.errors import (
    InvalidKeyError,
    InvalidOpcodeError,
    MemoryAccessError,
    StackOverflowError,
    StackUnderflowError,
)
from chip8.keyboard import Keypad
from chip8.opcode import decode
from chip8.quirks import get_quirks


def run(cpu: CPU, value: int) -> None:
    cpu.pc += 2
    cpu.execute(decode(value), cpu.pc - 2)


def test_flow_stack_and_skips() -> None:
    cpu = CPU()
    run(cpu, 0x220A)
    assert cpu.pc == 0x20A and cpu.stack == [0x202]
    run(cpu, 0x00EE)
    assert cpu.pc == 0x202 and cpu.stack == []
    cpu.v[1] = 7
    run(cpu, 0x3107)
    assert cpu.pc == 0x206
    run(cpu, 0x4108)
    assert cpu.pc == 0x20A
    cpu.v[2] = 7
    run(cpu, 0x5120)
    assert cpu.pc == 0x20E
    run(cpu, 0x9120)
    assert cpu.pc == 0x210


def test_jump_sets_pc() -> None:
    cpu = CPU()
    run(cpu, 0x1234)  # 1NNN: unconditional jump to NNN
    assert cpu.pc == 0x234


def test_set_add_load_index_and_register_copy() -> None:
    cpu = CPU()
    run(cpu, 0x61FE)
    run(cpu, 0x7105)
    assert cpu.v[1] == 3
    cpu.v[2] = 0x77
    run(cpu, 0x8120)
    assert cpu.v[1] == 0x77
    run(cpu, 0xA345)
    assert cpu.i == 0x345
    run(cpu, 0xF11E)
    assert cpu.i == 0x3BC


def test_stack_errors_and_invalid_opcode() -> None:
    cpu = CPU()
    with pytest.raises(StackUnderflowError):
        run(cpu, 0x00EE)
    cpu.stack[:] = [0] * 16
    with pytest.raises(StackOverflowError):
        run(cpu, 0x2200)
    with pytest.raises(InvalidOpcodeError):
        run(CPU(), 0xFFFF)


def test_arithmetic_logic_and_flags() -> None:
    cpu = CPU()
    cpu.v[1], cpu.v[2] = 250, 10
    run(cpu, 0x8124)
    assert cpu.v[1] == 4 and cpu.v[0xF] == 1
    cpu.v[1], cpu.v[2] = 3, 5
    run(cpu, 0x8125)
    assert cpu.v[1] == 254 and cpu.v[0xF] == 0
    cpu.v[1], cpu.v[2] = 3, 5
    run(cpu, 0x8127)
    assert cpu.v[1] == 2 and cpu.v[0xF] == 1
    cpu.v[1], cpu.v[2] = 0xF0, 0x0F
    run(cpu, 0x8121)
    assert cpu.v[1] == 0xFF
    run(cpu, 0x8122)
    assert cpu.v[1] == 0x0F
    run(cpu, 0x8123)
    assert cpu.v[1] == 0


def test_shift_quirks() -> None:
    modern = CPU(quirks=get_quirks("modern"))
    modern.v[1], modern.v[2] = 3, 0x80
    run(modern, 0x8126)
    assert (modern.v[1], modern.v[0xF]) == (1, 1)
    classic = CPU(quirks=get_quirks("classic"))
    classic.v[1], classic.v[2] = 3, 0x80
    run(classic, 0x812E)
    assert (classic.v[1], classic.v[0xF]) == (0, 1)


def test_modern_shift_left() -> None:
    cpu = CPU(quirks=get_quirks("modern"))
    cpu.v[1] = 0x81
    run(cpu, 0x811E)
    assert (cpu.v[1], cpu.v[0xF]) == (2, 1)


def test_draw_clear_random_and_jump() -> None:
    cpu = CPU(random_byte=lambda: 0xAB)
    cpu.i = 0x300
    cpu.memory.write(0x300, 0xF0)
    cpu.v[1], cpu.v[2] = 1, 2
    run(cpu, 0xD121)
    assert cpu.display.lit_pixels() == 4 and cpu.v[0xF] == 0
    run(cpu, 0xD121)
    assert cpu.display.lit_pixels() == 0 and cpu.v[0xF] == 1
    run(cpu, 0x00E0)
    run(cpu, 0xC10F)
    assert cpu.v[1] == 0x0B
    cpu.v[0] = 4
    run(cpu, 0xB300)
    assert cpu.pc == 0x304


def test_draw_zero_height_is_a_noop() -> None:
    cpu = CPU()
    cpu.i = 0x300
    cpu.v[1] = cpu.v[2] = 5
    run(cpu, 0xD120)  # DXY0 draws zero rows
    assert cpu.display.lit_pixels() == 0
    assert cpu.v[0xF] == 0


def test_snapshot_includes_requested_memory_range() -> None:
    cpu = CPU()
    cpu.memory.write(0x300, 0xAB)
    cpu.memory.write(0x301, 0xCD)
    snap = cpu.snapshot(memory_start=0x300, memory_length=2)
    assert snap["memory"] == {"start": 0x300, "bytes": "abcd"}


def test_input_timers_font_bcd_and_memory_transfer() -> None:
    keypad = Keypad()
    cpu = CPU(keypad=keypad)
    cpu.v[1] = 0xA
    keypad.press(0xA)
    run(cpu, 0xE19E)
    assert cpu.pc == 0x204
    keypad.release(0xA)
    run(cpu, 0xE1A1)
    assert cpu.pc == 0x208
    run(cpu, 0xF20A)  # FX0A drops the pre-wait edge and blocks for a fresh key
    keypad.press(0xA)
    keypad.release(0xA)
    run(cpu, 0xF20A)
    assert cpu.v[2] == 0xA
    cpu.v[3] = 9
    run(cpu, 0xF315)
    run(cpu, 0xF318)
    run(cpu, 0xF407)
    assert cpu.timers.delay == cpu.timers.sound == cpu.v[4] == 9
    cpu.v[5] = 0xA
    run(cpu, 0xF529)
    assert cpu.i == 0x50 + 50
    cpu.i = 0x300
    cpu.v[5] = 231
    run(cpu, 0xF533)
    assert cpu.memory.read_range(0x300, 3) == b"\x02\x03\x01"
    cpu.v[:3] = [1, 2, 3]
    run(cpu, 0xF255)
    cpu.v[:3] = [0, 0, 0]
    run(cpu, 0xF265)
    assert cpu.v[:3] == [1, 2, 3]


def test_classic_memory_transfer_increments_i() -> None:
    cpu = CPU(quirks=get_quirks("classic"))
    cpu.i = 0x300
    cpu.v[:2] = [0xAA, 0xBB]
    run(cpu, 0xF155)
    assert cpu.i == 0x302
    cpu.i = 0x300
    cpu.v[:2] = [0, 0]
    run(cpu, 0xF165)
    assert cpu.v[:2] == [0xAA, 0xBB]
    assert cpu.i == 0x302


def test_wait_for_key_repeats_instruction() -> None:
    cpu = CPU()
    original = cpu.pc
    run(cpu, 0xF10A)
    assert cpu.pc == original


def test_wait_for_key_needs_a_full_press_and_release() -> None:
    keypad = Keypad()
    cpu = CPU(keypad=keypad)
    keypad.press(0x5)  # held but not released yet: the wait must keep blocking
    run(cpu, 0xF00A)
    assert cpu.pc == 0x200 and cpu.v[0] == 0
    keypad.release(0x5)  # a completed press -> release edge satisfies FX0A
    run(cpu, 0xF00A)
    assert cpu.pc == 0x202 and cpu.v[0] == 0x5


def test_wait_for_key_ignores_input_buffered_before_the_wait() -> None:
    keypad = Keypad()
    cpu = CPU(keypad=keypad)
    keypad.press(0x7)
    keypad.release(0x7)  # a tap from earlier play, buffered as an edge
    run(cpu, 0xF00A)  # FX0A must discard it and keep blocking
    assert cpu.pc == 0x200 and cpu.v[0] == 0
    keypad.press(0x9)
    keypad.release(0x9)  # only a press made during the wait should count
    run(cpu, 0xF00A)
    assert cpu.pc == 0x202 and cpu.v[0] == 0x9


def test_key_skips_use_only_the_low_nibble() -> None:
    keypad = Keypad()
    cpu = CPU(keypad=keypad)
    keypad.press(0xA)
    cpu.v[1] = 0x1A  # high bits set; should still resolve to key 0xA
    run(cpu, 0xE19E)  # SKP V1: key pressed -> skip
    assert cpu.pc == 0x204


def test_classic_logic_ops_reset_vf() -> None:
    classic = CPU(quirks=get_quirks("classic"))
    classic.v[0xF], classic.v[1], classic.v[2] = 1, 0xF0, 0x0F
    run(classic, 0x8121)  # OR clears VF on the COSMAC VIP
    assert classic.v[1] == 0xFF and classic.v[0xF] == 0
    classic.v[0xF] = 1
    run(classic, 0x8122)  # AND
    assert classic.v[0xF] == 0
    classic.v[0xF] = 1
    run(classic, 0x8123)  # XOR
    assert classic.v[0xF] == 0
    modern = CPU(quirks=get_quirks("modern"))
    modern.v[0xF], modern.v[1], modern.v[2] = 1, 0xF0, 0x0F
    run(modern, 0x8121)
    assert modern.v[0xF] == 1  # modern leaves VF untouched


def test_jump_plus_v0_wraps_to_twelve_bits() -> None:
    cpu = CPU()
    cpu.v[0] = 0x05
    run(cpu, 0xBFFF)  # 0xFFF + 5 == 0x1004, wrapped into the 12-bit address space
    assert cpu.pc == 0x004


def test_ret_masks_pc_to_twelve_bits() -> None:
    cpu = CPU()
    cpu.stack.append(0x1500)
    run(cpu, 0x00EE)
    assert cpu.pc == 0x500


def test_fx1e_wraps_i_to_twelve_bits() -> None:
    cpu = CPU()
    cpu.i = 0xFFF
    cpu.v[1] = 0x10
    run(cpu, 0xF11E)
    assert cpu.i == 0x00F
    cpu.v[5] = 231
    cpu.pc = 0x202
    cpu.pc += 2
    cpu.execute(decode(0xF533), 0x202)
    assert cpu.memory.read_range(0x00F, 3) == b"\x02\x03\x01"


def test_fx55_at_memory_boundary_raises() -> None:
    cpu = CPU()
    cpu.i = 0xFF8
    cpu.v = list(range(16))
    cpu.pc = 0x202
    with pytest.raises(MemoryAccessError):
        cpu.execute(decode(0xFF55), 0x200)


def test_fx33_at_memory_boundary_raises() -> None:
    cpu = CPU()
    cpu.i = 0xFFE
    cpu.v[0] = 123
    cpu.pc = 0x202
    with pytest.raises(MemoryAccessError):
        cpu.execute(decode(0xF033), 0x200)


def test_fx65_at_memory_boundary_raises() -> None:
    cpu = CPU()
    cpu.i = 0xFF8
    cpu.v[0] = 0
    cpu.pc = 0x202
    with pytest.raises(MemoryAccessError):
        cpu.execute(decode(0xFF65), 0x200)


def test_memory_fault_propagates_through_cycle() -> None:
    cpu = CPU()
    cpu.i = 0xFF8
    cpu.v = list(range(16))
    cpu.memory.write(0x200, 0xFF)
    cpu.memory.write(0x201, 0x55)
    with pytest.raises(MemoryAccessError):
        cpu.cycle()


def test_fx0a_sets_awaiting_key_in_snapshot() -> None:
    cpu = CPU()
    run(cpu, 0xF00A)
    assert cpu.awaiting_key is True
    assert cpu.snapshot()["awaiting_key"] is True


def test_invalid_key_raises_chip8_error() -> None:
    keypad = Keypad()
    with pytest.raises(InvalidKeyError):
        keypad.press(0x10)
    with pytest.raises(InvalidKeyError):
        keypad.release(0x10)


def test_reset_clears_state_but_keeps_memory() -> None:
    cpu = CPU()
    cpu.load_rom(bytes.fromhex("6001 1200"))
    cpu.cycle()
    cpu.cycle()
    cpu.v[3] = 0xAB
    cpu.timers.delay = 9
    cpu.stack.append(0x300)
    cpu.reset()
    assert cpu.pc == 0x200
    assert cpu.v == [0] * 16
    assert cpu.stack == [] and cpu.cycles == 0
    assert cpu.timers.delay == 0 and cpu.timers.sound == 0
    assert cpu.memory.read_word(0x200) == 0x6001  # font and ROM survive a reset


def test_snapshot_can_include_quirks_and_memory() -> None:
    cpu = CPU()
    cpu.v[0] = 0x42
    snap = cpu.snapshot(memory_start=0x200, memory_length=2, include_quirks=True)
    quirks = snap["quirks"]
    assert isinstance(quirks, dict)
    assert quirks["name"] == "modern"
    assert snap["memory"] == {"start": 0x200, "bytes": cpu.memory.read_range(0x200, 2).hex()}


def test_fetch_returns_opcode_and_advances_pc() -> None:
    cpu = CPU()
    cpu.memory.write(0x200, 0x60)
    cpu.memory.write(0x201, 0x01)
    address, opcode = cpu.fetch()
    assert address == 0x200
    assert opcode.value == 0x6001
    assert cpu.pc == 0x202


def test_cxnn_with_zero_mask_always_stores_zero() -> None:
    cpu = CPU(random_byte=lambda: 0xFF)
    run(cpu, 0xC000)
    assert cpu.v[0] == 0


def test_load_rom_delegates_to_memory() -> None:
    cpu = CPU()
    cpu.load_rom(bytes.fromhex("6001"))
    assert cpu.memory.read_word(0x200) == 0x6001


def test_fx65_loads_registers_from_memory() -> None:
    cpu = CPU()
    cpu.i = 0x300
    cpu.memory.write(0x300, 0x11)
    cpu.memory.write(0x301, 0x22)
    run(cpu, 0xF165)
    assert cpu.v[0] == 0x11
    assert cpu.v[1] == 0x22
