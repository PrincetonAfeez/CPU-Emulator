"""The CHIP-8 CPU: fetch-decode-execute, registers, stack, and opcode handlers."""

from __future__ import annotations

import random
from collections.abc import Callable
from dataclasses import dataclass, field

from .display import FrameBuffer
from .errors import InvalidOpcodeError, StackOverflowError, StackUnderflowError
from .keyboard import Keypad
from .memory import FONT_START, PROGRAM_START, Memory
from .opcode import Opcode, decode
from .quirks import QuirkProfile, get_quirks
from .timers import Timers

RandomByte = Callable[[], int]


def _default_random_byte() -> int:
    """Non-deterministic default; tests and headless runs inject a seeded source."""
    return random.randrange(256)


@dataclass(slots=True)
class CPU:
    memory: Memory = field(default_factory=Memory)
    display: FrameBuffer = field(default_factory=FrameBuffer)
    keypad: Keypad = field(default_factory=Keypad)
    timers: Timers = field(default_factory=Timers)
    quirks: QuirkProfile = field(default_factory=lambda: get_quirks("modern"))
    random_byte: RandomByte = field(default=_default_random_byte)
    v: list[int] = field(default_factory=lambda: [0] * 16)
    i: int = 0
    pc: int = PROGRAM_START
    stack: list[int] = field(default_factory=list)
    cycles: int = 0
    # True while an FX0A instruction is blocking, so input buffered before the
    # wait began is discarded once and only a fresh key press satisfies it.
    awaiting_key: bool = False

    def reset(self) -> None:
        """Restart execution from power-on state, keeping loaded memory.

        Registers, stack, display, timers, and input are cleared and PC returns
        to 0x200. Memory (font plus any loaded ROM) is preserved; reload a ROM
        explicitly if a pristine address space is required.
        """
        self.display.clear()
        self.keypad.reset()
        self.timers.reset()
        self.v[:] = [0] * 16
        self.i = 0
        self.pc = PROGRAM_START
        self.stack.clear()
        self.cycles = 0
        self.awaiting_key = False

    def load_rom(self, rom: bytes) -> None:
        self.memory.load_rom(rom)

    def fetch(self) -> tuple[int, Opcode]:
        address = self.pc
        opcode = decode(self.memory.read_word(address))
        self.pc = (self.pc + 2) & 0xFFF
        return address, opcode

    def cycle(self) -> tuple[int, Opcode]:
        address, opcode = self.fetch()
        self.execute(opcode, address)
        self.cycles += 1
        return address, opcode

    def execute(self, op: Opcode, address: int) -> None:
        if not op.is_known:
            raise InvalidOpcodeError(op.value, address)

        h, x, y, n, nn, nnn = op.high, op.x, op.y, op.n, op.nn, op.nnn
        if op.value == 0x00E0:
            self.display.clear()
        elif op.value == 0x00EE:
            if not self.stack:
                raise StackUnderflowError(f"RET at 0x{address:03X} with an empty stack")
            self.pc = self.stack.pop() & 0xFFF
        elif h == 0x1:
            self.pc = nnn
        elif h == 0x2:
            if len(self.stack) >= 16:
                raise StackOverflowError(f"CALL at 0x{address:03X} exceeds 16 stack levels")
            self.stack.append(self.pc)
            self.pc = nnn
        elif h == 0x3:
            self._skip(self.v[x] == nn)
        elif h == 0x4:
            self._skip(self.v[x] != nn)
        elif h == 0x5:
            self._skip(self.v[x] == self.v[y])
        elif h == 0x6:
            self.v[x] = nn
        elif h == 0x7:
            self.v[x] = (self.v[x] + nn) & 0xFF
        elif h == 0x8:
            self._execute_8(x, y, n)
        elif h == 0x9:
            self._skip(self.v[x] != self.v[y])
        elif h == 0xA:
            self.i = nnn
        elif h == 0xB:
            # BNNN jumps to NNN + V0. This is the COSMAC/standard behavior and
            # the most ROM-compatible choice, so both quirk profiles use it.
            self.pc = (nnn + self.v[0]) & 0xFFF
        elif h == 0xC:
            self.v[x] = self.random_byte() & nn & 0xFF
        elif h == 0xD:
            sprite = self.memory.read_range(self.i & 0xFFF, n)
            collision = self.display.draw_sprite(
                self.v[x], self.v[y], sprite, wrap=self.quirks.draw_wrap
            )
            self.v[0xF] = int(collision)
        elif h == 0xE:
            # Only the low nibble of VX names a key, matching FX29/FX0A.
            key = self.v[x] & 0xF
            if nn == 0x9E:
                self._skip(self.keypad.is_pressed(key))
            else:
                self._skip(not self.keypad.is_pressed(key))
        elif h == 0xF:
            self._execute_f(x, nn)

    def _skip(self, condition: bool) -> None:
        if condition:
            self.pc = (self.pc + 2) & 0xFFF

    def _maybe_reset_flag(self) -> None:
        # COSMAC VIP cleared VF after the logical ops 8XY1/2/3; later
        # interpreters left it untouched. The classic profile restores it.
        if self.quirks.logic_resets_flag:
            self.v[0xF] = 0

    def _execute_8(self, x: int, y: int, n: int) -> None:
        if n == 0:
            self.v[x] = self.v[y]
        elif n == 1:
            self.v[x] |= self.v[y]
            self._maybe_reset_flag()
        elif n == 2:
            self.v[x] &= self.v[y]
            self._maybe_reset_flag()
        elif n == 3:
            self.v[x] ^= self.v[y]
            self._maybe_reset_flag()
        elif n == 4:
            total = self.v[x] + self.v[y]
            self.v[x] = total & 0xFF
            self.v[0xF] = int(total > 0xFF)
        elif n == 5:
            left, right = self.v[x], self.v[y]
            self.v[x] = (left - right) & 0xFF
            self.v[0xF] = int(left >= right)
        elif n == 6:
            source = self.v[y] if self.quirks.shift_uses_vy else self.v[x]
            self.v[x] = source >> 1
            self.v[0xF] = source & 1
        elif n == 7:
            left, right = self.v[y], self.v[x]
            self.v[x] = (left - right) & 0xFF
            self.v[0xF] = int(left >= right)
        elif n == 0xE:
            source = self.v[y] if self.quirks.shift_uses_vy else self.v[x]
            self.v[x] = (source << 1) & 0xFF
            self.v[0xF] = (source >> 7) & 1

    def _execute_f(self, x: int, nn: int) -> None:
        if nn == 0x07:
            self.v[x] = self.timers.delay
        elif nn == 0x0A:
            if not self.awaiting_key:
                # Entering the wait: drop any key edges buffered during earlier
                # play so only a press made from now on counts.
                self.awaiting_key = True
                self.keypad.begin_wait()
            key = self.keypad.next_key_press()
            if key is None:
                self.pc = (self.pc - 2) & 0xFFF
            else:
                self.v[x] = key
                self.awaiting_key = False
        elif nn == 0x15:
            self.timers.delay = self.v[x]
        elif nn == 0x18:
            self.timers.sound = self.v[x]
        elif nn == 0x1E:
            self.i = (self.i + self.v[x]) & 0xFFF
        elif nn == 0x29:
            self.i = FONT_START + (self.v[x] & 0xF) * 5
        elif nn == 0x33:
            value = self.v[x]
            base = self.i & 0xFFF
            self.memory.write(base, value // 100)
            self.memory.write(base + 1, (value // 10) % 10)
            self.memory.write(base + 2, value % 10)
        elif nn == 0x55:
            base = self.i & 0xFFF
            for register in range(x + 1):
                self.memory.write(base + register, self.v[register])
            if self.quirks.load_store_increment_i:
                self.i = (base + x + 1) & 0xFFF
        elif nn == 0x65:
            base = self.i & 0xFFF
            for register in range(x + 1):
                self.v[register] = self.memory.read(base + register)
            if self.quirks.load_store_increment_i:
                self.i = (base + x + 1) & 0xFFF

    def snapshot(
        self,
        memory_start: int | None = None,
        memory_length: int = 0,
        *,
        include_quirks: bool = False,
    ) -> dict[str, object]:
        snapshot: dict[str, object] = {
            "pc": self.pc,
            "i": self.i,
            "v": list(self.v),
            "stack": list(self.stack),
            "delay_timer": self.timers.delay,
            "sound_timer": self.timers.sound,
            "cycles": self.cycles,
            "awaiting_key": self.awaiting_key,
        }
        if include_quirks:
            snapshot["quirks"] = self.quirks.describe()
        if memory_start is not None:
            snapshot["memory"] = {
                "start": memory_start,
                "bytes": self.memory.read_range(memory_start, memory_length).hex(),
            }
        return snapshot
