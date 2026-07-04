# 0003 — Tamper-evident traces via SHA-256 hash chaining

Status: Accepted

## Context

The project wants an observable, verifiable record of execution: a reviewer
should be able to confirm that a trace was produced by a specific ROM and was not
edited afterward. This is an exercise in applying standard cryptographic hash
primitives honestly — the emulator itself does not need encryption.

## Decision

`--trace` writes one JSON record per cycle (`src/chip8/trace.py`) using format
`chip8-trace-v2`. Each record contains:

- `pc` and `opcode` for the executed instruction
- `before_pc` (program counter before the instruction)
- `after_pc` and `cycles` (program counter and cycle count after the instruction)
- post-instruction `v`, `i`, `delay_timer`, `sound_timer`, `stack`, and
  `awaiting_key`
- `previous_hash` linking to the prior record

The record's own `hash` is the SHA-256 of its canonical (sorted, compact) JSON
payload. The chain is seeded from the SHA-256 of the header, so the recorded
`rom_sha256` and quirk profile are themselves covered by the chain.
`trace-verify` recomputes every link and validates the full header and record
schemas: the header must include `format`, `rom_sha256`, and `quirks`; `rom_sha256`
must be a 64-character lowercase hex string; `quirks` must contain exactly the
fields emitted by `QuirkProfile.describe()` with the expected types (`name` is
`"classic"` or `"modern"`; the four boolean flags). Extra top-level header
fields are allowed and participate in the hash chain. Each record field is
type- and range-checked (CHIP-8 addresses, byte values, non-negative counters,
and 64-character lowercase hex digests for `previous_hash` and `hash`). Extra
record fields are also allowed and participate in the recomputed record hash.
`--rom` additionally checks the header hash against an actual ROM file.

Version history: `chip8-trace-v1` records lacked `before_pc` and `awaiting_key`;
v2 is the current schema.

## Consequences

- Editing any record — or the header's ROM identity — breaks a hash link and is
  detected (covered by tests in `tests/unit/test_tools.py`).
- Verification needs only the standard library (`hashlib`, `json`); there are no
  third-party dependencies.
- Traces are reproducible only in deterministic mode (seeded RNG + deterministic
  clock, see ADR 0001); interactive traces depend on wall-clock timing and are
  not expected to match across runs.
- HMAC-keyed signing is a possible extension but is out of scope here.
