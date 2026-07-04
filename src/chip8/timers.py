"""Delay and sound timers that count down at 60 Hz, decoupled from CPU speed."""

from __future__ import annotations

from dataclasses import dataclass

TIMER_HZ = 60.0


@dataclass(slots=True)
class Timers:
    delay: int = 0
    sound: int = 0
    _last_time: float | None = None
    _fraction: float = 0.0

    def update(self, now: float) -> int:
        if self._last_time is None:
            self._last_time = now
            return 0
        elapsed = max(0.0, now - self._last_time)
        self._last_time = now
        ticks_float = elapsed * TIMER_HZ + self._fraction
        ticks = int(ticks_float)
        self._fraction = ticks_float - ticks
        self.tick(ticks)
        return ticks

    def tick(self, count: int = 1) -> None:
        if count <= 0:
            return
        self.delay = max(0, self.delay - count)
        self.sound = max(0, self.sound - count)

    def reset(self) -> None:
        self.delay = 0
        self.sound = 0
        self._last_time = None
        self._fraction = 0.0

