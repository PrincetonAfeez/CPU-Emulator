"""16-key hex keypad and a cross-platform non-blocking terminal adapter."""

from __future__ import annotations

import os
import sys
import time
from dataclasses import dataclass, field
from importlib import import_module
from typing import TextIO

from .errors import InputUnavailableError, InvalidKeyError

KEY_MAP = {
    "1": 0x1, "2": 0x2, "3": 0x3, "4": 0xC,
    "q": 0x4, "w": 0x5, "e": 0x6, "r": 0xD,
    "a": 0x7, "s": 0x8, "d": 0x9, "f": 0xE,
    "z": 0xA, "x": 0x0, "c": 0xB, "v": 0xF,
}


@dataclass(slots=True)
class Keypad:
    pressed: set[int] = field(default_factory=set)
    # Completed press -> release edges, oldest first. FX0A consumes these, so
    # only a key that was actually pressed *and let go* satisfies a wait.
    # TerminalKeypad simulates release after a short hold; see README "Display
    # and input" for the rationale (avoids stale key edges before a wait).
    _released: list[int] = field(default_factory=list)

    def is_pressed(self, key: int) -> bool:
        return key in self.pressed

    def press(self, key: int) -> None:
        if not 0 <= key <= 0xF:
            raise InvalidKeyError(f"CHIP-8 keys are 0x0 through 0xF, got 0x{key:X}")
        self.pressed.add(key)

    def release(self, key: int) -> None:
        if not 0 <= key <= 0xF:
            raise InvalidKeyError(f"CHIP-8 keys are 0x0 through 0xF, got 0x{key:X}")
        if key in self.pressed:
            self.pressed.discard(key)
            self._released.append(key)

    def next_key_press(self) -> int | None:
        return self._released.pop(0) if self._released else None

    def begin_wait(self) -> None:
        """Discard buffered key edges so FX0A waits for a genuinely new press."""
        self._released.clear()

    def reset(self) -> None:
        self.pressed.clear()
        self._released.clear()


class TerminalKeypad(Keypad):
    """Small cross-platform non-blocking terminal adapter.

    Terminals do not report key-up events, so a key remains down briefly after
    each character. That pulse is enough for CHIP-8 key-skip instructions.
    """

    def __init__(self, hold_seconds: float = 0.12) -> None:
        super().__init__()
        self.hold_seconds = hold_seconds
        self._expires: dict[int, float] = {}
        self._old_termios: object | None = None

    def __enter__(self) -> TerminalKeypad:
        # Require a real terminal on every platform; piped/redirected stdin has
        # no key state to read.
        if not sys.stdin.isatty():
            raise InputUnavailableError("interactive input requires a terminal")
        if os.name != "nt":
            termios = import_module("termios")
            tty = import_module("tty")
            self._old_termios = termios.tcgetattr(sys.stdin)
            tty.setcbreak(sys.stdin.fileno())
        return self

    def __exit__(self, *_: object) -> None:
        if os.name != "nt" and self._old_termios is not None:
            termios = import_module("termios")
            termios.tcsetattr(sys.stdin, termios.TCSADRAIN, self._old_termios)

    def poll(self, stream: TextIO | None = None) -> None:
        stream = stream if stream is not None else sys.stdin
        now = time.monotonic()
        for key, expiry in list(self._expires.items()):
            if now >= expiry:
                self.release(key)
                del self._expires[key]

        characters: list[str] = []
        if os.name == "nt":
            import msvcrt

            while msvcrt.kbhit():
                characters.append(msvcrt.getwch())
        else:
            import select

            while select.select([stream], [], [], 0)[0]:
                characters.append(stream.read(1))

        for character in characters:
            if character == "\x03":
                raise KeyboardInterrupt
            mapped = KEY_MAP.get(character.lower())
            if mapped is not None:
                self.press(mapped)
                self._expires[mapped] = now + self.hold_seconds
