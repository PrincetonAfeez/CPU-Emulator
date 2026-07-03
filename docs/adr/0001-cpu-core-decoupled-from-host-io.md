# 0001 — CPU core decoupled from host I/O

Status: Accepted

## Context

A CHIP-8 interpreter touches several host-facing services: a clock (for 60 Hz
timers), a random byte source (`CXNN`), a display, and a keypad. If the CPU
reached for `time`, `random`, the terminal, and `msvcrt`/`termios` directly,
the fetch-decode-execute core could not be tested without a real terminal, and
runs would be non-deterministic.

## Decision

The `CPU` owns only emulated state and takes its host services by injection:
`memory`, `display`, `keypad`, `timers`, `quirks`, and a `random_byte` callable
are constructor fields (`src/chip8/cpu.py`). `Machine` wires real implementations
for normal use and a `DeterministicClock` / seeded RNG / headless framebuffer for
tests (`src/chip8/machine.py`). The terminal- and platform-specific code lives
behind `TerminalKeypad` and `enable_ansi_console`, never in the CPU.

## Consequences

- The CPU is testable headlessly; the unit suite never opens a terminal.
- Headless runs are reproducible (fixed seed + deterministic clock), which also
  makes hash-chained traces (ADR 0003) reproducible.
- A small amount of wiring lives in `Machine.create` instead of the CPU.
- The same decoded `Opcode` feeds execution, disassembly, CFG, and tracing, so
  there is one decoder rather than several that could drift.
