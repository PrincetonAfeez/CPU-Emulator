"""Unit tests for the Timers module."""

from chip8.timers import Timers


def test_timers_are_decoupled_and_tick_at_60hz() -> None:
    timers = Timers(delay=5, sound=3)
    timers.update(10.0)
    assert timers.update(10.05) == 3
    assert timers.delay == 2 and timers.sound == 0


def test_update_first_call_initializes_clock() -> None:
    timers = Timers(delay=10)
    assert timers.update(1.0) == 0
    assert timers.delay == 10


def test_tick_ignores_non_positive_counts() -> None:
    timers = Timers(delay=5, sound=5)
    timers.tick(0)
    timers.tick(-3)
    assert timers.delay == 5 and timers.sound == 5


def test_reset_clears_fractional_state() -> None:
    timers = Timers(delay=10)
    timers.update(0.0)
    timers.update(0.01)
    timers.reset()
    assert timers.delay == 0 and timers.sound == 0
    assert timers._last_time is None
    assert timers._fraction == 0.0

