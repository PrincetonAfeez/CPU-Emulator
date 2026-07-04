"""Unit tests for the Memory and Display modules."""

import pytest

from chip8.display import FrameBuffer
from chip8.errors import MemoryAccessError, RomLoadError
from chip8.memory import FONT_DATA, FONT_START, MEMORY_SIZE, Memory


def test_font_and_rom_bounds() -> None:
    memory = Memory()
    assert memory.read_range(FONT_START, len(FONT_DATA)) == FONT_DATA
    with pytest.raises(RomLoadError):
        memory.load_rom(bytes(MEMORY_SIZE))
    with pytest.raises(MemoryAccessError):
        memory.read_word(0xFFF)


def test_shorter_rom_reload_clears_stale_tail() -> None:
    memory = Memory()
    memory.load_rom(bytes([0xFF] * 100))
    memory.load_rom(bytes([0x60, 0x01]))
    assert memory.read(0x200) == 0x60
    assert memory.read(0x201) == 0x01
    assert memory.read(0x202) == 0x00
    assert memory.read(0x263) == 0x00


def test_custom_load_address_clears_stale_tail() -> None:
    memory = Memory()
    memory.load_rom(bytes([0xAA] * 50), start=0x300)
    memory.load_rom(bytes([0xBB, 0xCC]), start=0x300)
    assert memory.read(0x300) == 0xBB
    assert memory.read(0x301) == 0xCC
    assert memory.read(0x302) == 0x00


def test_overlapping_load_regions_are_rejected() -> None:
    memory = Memory()
    memory.load_rom(bytes([0xAA] * 16), start=0x300)
    with pytest.raises(RomLoadError, match="overlaps prior load"):
        memory.load_rom(bytes([0xBB] * 16), start=0x308)


def test_memory_rejects_wrong_sized_buffer() -> None:
    with pytest.raises(ValueError):
        Memory(bytearray(10))


def test_xor_drawing_collision_and_wrap() -> None:
    display = FrameBuffer()
    assert not display.draw_sprite(63, 31, b"\xC0", wrap=True)
    assert display.pixels[31][63] == 1
    assert display.pixels[31][0] == 1
    assert display.draw_sprite(63, 31, b"\xC0", wrap=True)
    assert display.lit_pixels() == 0


def test_clip_mode_wraps_origin_but_clips_body() -> None:
    display = FrameBuffer()
    # The draw origin always reduces modulo the screen, even when clipping.
    assert not display.draw_sprite(66, 0, b"\x80", wrap=False)  # 66 % 64 == 2
    assert display.pixels[0][2] == 1
    assert display.lit_pixels() == 1
    # The sprite body still clips: a second row at y == 32 is dropped.
    display.clear()
    assert not display.draw_sprite(0, 31, b"\x80\x80", wrap=False)
    assert display.pixels[31][0] == 1
    assert display.lit_pixels() == 1


def test_render_maps_half_blocks_to_the_correct_row() -> None:
    display = FrameBuffer()
    display.pixels[0][0] = 1  # top pixel of the first row-pair
    display.pixels[1][1] = 1  # bottom pixel of the first row-pair
    display.pixels[0][2] = display.pixels[1][2] = 1  # both halves
    line = display.render().split("\n")[0]
    assert line[0] == "▀"  # upper half block for a lit top pixel
    assert line[1] == "▄"  # lower half block for a lit bottom pixel
    assert line[2] == "█"  # full block when both pixels are lit
    assert line[3] == " "  # blank when neither pixel is lit


def test_empty_rom_load_is_rejected() -> None:
    with pytest.raises(RomLoadError, match="empty"):
        Memory().load_rom(b"")


def test_memory_write_and_read_bytes() -> None:
    memory = Memory()
    memory.write(0x400, 0xAB)
    assert memory.read(0x400) == 0xAB
    assert memory.read_range(0x400, 1) == b"\xAB"


def test_clip_mode_skips_pixels_past_right_edge() -> None:
    display = FrameBuffer()
    # Sprite bit at x+7 == 64 should clip, not draw.
    assert not display.draw_sprite(57, 0, b"\x01", wrap=False)
    assert display.lit_pixels() == 0

