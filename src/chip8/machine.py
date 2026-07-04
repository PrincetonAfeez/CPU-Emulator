"""Machine: wires the CPU to a clock and host loop (headless and interactive)."""

from __future__ import annotations

import contextlib
import os
import random
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from .cpu import CPU
from .debug import format_transition
from .display import HEIGHT, FrameBuffer
from .keyboard import Keypad, TerminalKeypad
from .memory import Memory
from .opcode import Opcode
from .quirks import QuirkProfile, get_quirks
from .timers import Timers
from .trace import TraceWriter


def enable_ansi_console() -> None:
    """Best-effort: let legacy Windows consoles show ANSI codes and block glyphs.

    Modern terminals need virtual-terminal processing enabled, and a non-UTF-8
    console raises ``UnicodeEncodeError`` on the half-block characters. Both are
    no-ops elsewhere and failures are ignored so headless runs never break.
    """
    reconfigure = getattr(sys.stdout, "reconfigure", None)
    if reconfigure is not None:
        with contextlib.suppress(ValueError, OSError):
            reconfigure(encoding="utf-8")
    if os.name != "nt":
        return
    try:
        import ctypes

        kernel32 = ctypes.windll.kernel32
        handle = kernel32.GetStdHandle(-11)  # STD_OUTPUT_HANDLE
        mode = ctypes.c_uint32()
        if kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
            kernel32.SetConsoleMode(handle, mode.value | 0x0004)  # ENABLE_VT_PROCESSING
    except (OSError, AttributeError):
        pass


class Clock(Protocol):
    def monotonic(self) -> float: ...
    def sleep(self, seconds: float) -> None: ...


class RealClock:
    def monotonic(self) -> float:
        return time.monotonic()

    def sleep(self, seconds: float) -> None:
        time.sleep(max(0.0, seconds))


@dataclass(slots=True)
class DeterministicClock:
    now: float = 0.0

    def monotonic(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.now += max(0.0, seconds)


@dataclass(slots=True)
class Machine:
    cpu: CPU
    clock: Clock = field(default_factory=RealClock)

    @classmethod
    def create(
        cls,
        *,
        quirks: QuirkProfile | None = None,
        keypad: Keypad | None = None,
        clock: Clock | None = None,
        seed: int | None = None,
    ) -> Machine:
        rng = random.Random(seed)
        cpu = CPU(
            memory=Memory(),
            display=FrameBuffer(),
            keypad=keypad or Keypad(),
            timers=Timers(),
            quirks=quirks or get_quirks("modern"),
            random_byte=lambda: rng.randrange(256),
        )
        return cls(cpu=cpu, clock=clock or RealClock())

    def load_rom_file(self, path: Path) -> bytes:
        rom = path.read_bytes()
        self.cpu.load_rom(rom)
        return rom

    def step(self) -> tuple[int, Opcode]:
        self.cpu.timers.update(self.clock.monotonic())
        return self.cpu.cycle()

    def run_headless(
        self,
        cycles: int,
        *,
        speed: int = 700,
        trace: TraceWriter | None = None,
    ) -> None:
        for _ in range(cycles):
            before = self.cpu.snapshot()
            address, opcode = self.step()
            if trace is not None:
                trace.record(address, opcode.value, before, self.cpu.snapshot())
            self.clock.sleep(1.0 / speed)

    def run_interactive(
        self,
        *,
        speed: int = 700,
        max_cycles: int | None = None,
        step_mode: bool = False,
        trace: TraceWriter | None = None,
    ) -> None:
        keypad = self.cpu.keypad
        if not isinstance(keypad, TerminalKeypad):
            raise TypeError("interactive execution requires TerminalKeypad")
        cycle_period = 1.0 / speed
        next_cycle = self.clock.monotonic()
        sound_was_on = False
        enable_ansi_console()
        with keypad:
            sys.stdout.write("\x1b[2J\x1b[H")
            sys.stdout.flush()
            while max_cycles is None or self.cpu.cycles < max_cycles:
                keypad.poll()
                now = self.clock.monotonic()
                if now < next_cycle:
                    while now < next_cycle:
                        keypad.poll()
                        self.clock.sleep(min(next_cycle - now, 0.002))
                        now = self.clock.monotonic()
                    continue
                before = self.cpu.snapshot()
                address, opcode = self.step()
                after = self.cpu.snapshot()
                if trace is not None:
                    trace.record(address, opcode.value, before, after)
                if self.cpu.display.dirty or step_mode:
                    # Redraw the pixel grid only when it changed, to avoid flicker.
                    sys.stdout.write("\x1b[H" + self.cpu.display.render())
                # Refresh the status line every cycle (cheap) so PC, timers, and
                # the sound state stay live even while the framebuffer is idle.
                sound_on = self.cpu.timers.sound > 0
                sys.stdout.write(
                    f"\x1b[{HEIGHT // 2 + 1};1H"
                    f"PC={self.cpu.pc:03X} I={self.cpu.i:03X} "
                    f"DT={self.cpu.timers.delay:02X} ST={self.cpu.timers.sound:02X} "
                    f"{opcode.mnemonic():<14} quirks={self.cpu.quirks.name} "
                    f"{'[SND]' if sound_on else '     '}\x1b[K"
                )
                sys.stdout.flush()
                if sound_on and not sound_was_on:
                    sys.stdout.write("\a")
                    sys.stdout.flush()
                sound_was_on = sound_on
                if step_mode:
                    registers = " ".join(
                        f"V{index:X}={value:02X}" for index, value in enumerate(self.cpu.v)
                    )
                    sys.stdout.write(
                        "\n"
                        + registers
                        + f"\nstack={[f'{value:03X}' for value in self.cpu.stack]}\n"
                        + format_transition(address, opcode, before, after)
                        + "\n"
                        + "Press Enter for next instruction (Ctrl+C to quit)..."
                    )
                    sys.stdout.flush()
                    input()
                next_cycle += cycle_period
