# 0004 — Strict 12-bit memory addressing

Status: Accepted

## Context

CHIP-8 programs can advance `PC`, `I`, and stack return addresses in ways that
exceed the 4096-byte address space. Real hardware and emulators disagree about
whether addresses wrap silently or fault. This project must pick one rule for
portfolio clarity and testability.

## Decision

All **program addresses** (`PC`, `RET` targets, `BNNN` results) are reduced
modulo 4096 (`& 0xFFF`). The **index register** used for memory operations is
also kept within 12 bits for `FX1E`, `FX33`, `FX55`, `FX65`, and sprite reads.

**Memory access itself is strict:** reads and writes outside `0x000..0xFFF` raise
`MemoryAccessError` rather than wrapping. Bulk transfers such as `LD [I], VF`
when `I` is near `0xFFF` therefore abort instead of wrapping into low memory.

## Consequences

- Behavior is predictable and easy to test; faults surface as explicit emulator
  errors (CLI exit code 2).
- Some pathological or incorrectly authored ROMs that rely on silent wrap may
  fail where other emulators succeed — an acceptable trade-off for an academic
  "strict machine" model documented in the README.
- Portfolio reviewers can distinguish intentional strictness from accidental bugs
  via unit tests for boundary faults and this ADR.
