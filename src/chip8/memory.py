"""4 KB address space: font loading, ROM loading, and bounds-checked access."""

from __future__ import annotations

from dataclasses import dataclass, field

from .errors import MemoryAccessError, RomLoadError

MEMORY_SIZE = 4096
PROGRAM_START = 0x200
FONT_START = 0x50

# Five bytes per hexadecimal digit, 0 through F.
FONT_DATA = bytes(
    [
        0xF0, 0x90, 0x90, 0x90, 0xF0,
        0x20, 0x60, 0x20, 0x20, 0x70,
        0xF0, 0x10, 0xF0, 0x80, 0xF0,
        0xF0, 0x10, 0xF0, 0x10, 0xF0,
        0x90, 0x90, 0xF0, 0x10, 0x10,
        0xF0, 0x80, 0xF0, 0x10, 0xF0,
        0xF0, 0x80, 0xF0, 0x90, 0xF0,
        0xF0, 0x10, 0x20, 0x40, 0x40,
        0xF0, 0x90, 0xF0, 0x90, 0xF0,
        0xF0, 0x90, 0xF0, 0x10, 0xF0,
        0xF0, 0x90, 0xF0, 0x90, 0x90,
        0xE0, 0x90, 0xE0, 0x90, 0xE0,
        0xF0, 0x80, 0x80, 0x80, 0xF0,
        0xE0, 0x90, 0x90, 0x90, 0xE0,
        0xF0, 0x80, 0xF0, 0x80, 0xF0,
        0xF0, 0x80, 0xF0, 0x80, 0x80,
    ]
)


@dataclass(slots=True)
class Memory:
    data: bytearray = field(default_factory=lambda: bytearray(MEMORY_SIZE))
    # Per load address: end of the last ROM loaded there (clears stale tail bytes).
    _loaded_ends: dict[int, int] = field(default_factory=dict, init=False, compare=False)

    def __post_init__(self) -> None:
        if len(self.data) != MEMORY_SIZE:
            raise ValueError(f"memory must be exactly {MEMORY_SIZE} bytes")
        self.data[FONT_START : FONT_START + len(FONT_DATA)] = FONT_DATA

    def _check(self, address: int, length: int = 1) -> None:
        if address < 0 or length < 0 or address + length > MEMORY_SIZE:
            raise MemoryAccessError(
                f"memory access 0x{address:03X}..0x{address + length - 1:03X} "
                f"is outside 0x000..0xFFF"
            )

    def read(self, address: int) -> int:
        self._check(address)
        return self.data[address]

    def write(self, address: int, value: int) -> None:
        self._check(address)
        self.data[address] = value & 0xFF

    def read_word(self, address: int) -> int:
        self._check(address, 2)
        return (self.data[address] << 8) | self.data[address + 1]

    def read_range(self, address: int, length: int) -> bytes:
        self._check(address, length)
        return bytes(self.data[address : address + length])

    def load_rom(self, rom: bytes, start: int = PROGRAM_START) -> None:
        """Load a ROM into memory, clearing any tail left by a shorter prior load."""
        if not rom:
            raise RomLoadError("ROM is empty")
        if start < 0 or start + len(rom) > MEMORY_SIZE:
            maximum = MEMORY_SIZE - start
            raise RomLoadError(f"ROM is {len(rom)} bytes; maximum at 0x{start:03X} is {maximum}")
        new_end = start + len(rom)
        for other_start, other_end in self._loaded_ends.items():
            if other_start == start:
                continue
            if start < other_end and new_end > other_start:
                raise RomLoadError(
                    f"ROM load 0x{start:03X}..0x{new_end - 1:03X} overlaps prior load "
                    f"0x{other_start:03X}..0x{other_end - 1:03X}"
                )
        previous_end = self._loaded_ends.get(start, start)
        if new_end < previous_end:
            self.data[new_end:previous_end] = b"\x00" * (previous_end - new_end)
        self.data[start:new_end] = rom
        self._loaded_ends[start] = new_end

