# Architecture Decision Record
## App — CPU Emulator
**Emulation Systems Group | Document 1 of 5**
**Status: Accepted**

---

## Context

The Emulation Systems group requires a portfolio-ready CPU emulator that demonstrates instruction decoding, register-width discipline, checked memory, stack behavior, timers, graphics, keyboard input, compatibility quirks, deterministic testing, debugging, and operational tooling.

The project is a complete, CLI-first **CHIP-8 emulator**. It runs ROMs in the terminal, supports deterministic headless execution, and includes a shared disassembler, step debugger, static control-flow graph analyzer, subprocess ROM smoke-test runner, SHA-256 ROM identity, and tamper-evident execution traces.

CHIP-8 provides a well-scoped machine model:

- 4096 bytes of memory
- sixteen 8-bit registers (`V0`–`VF`)
- 12-bit `I` and `PC`
- a checked 16-level return stack
- independent 60 Hz delay and sound timers
- a 64×32 XOR framebuffer
- a hexadecimal keypad
- historically different interpreter behaviors

## Decision Drivers

- Show a real fetch/decode/execute loop.
- Keep emulated hardware independent from host terminal details.
- Make headless behavior reproducible in CI.
- Prevent multiple tools from implementing subtly different opcode decoders.
- State compatibility choices explicitly.
- Treat ROMs, traces, memory addresses, and terminal input defensively.

## Decisions

### 1. Emulate CHIP-8 rather than invent a custom CPU

CHIP-8 supplies known ROM behavior, public conformance material, recognizable opcodes, and real compatibility questions. This makes the capstone externally verifiable.

### 2. Keep the product CLI-first

The primary interface is `chip8`. A GUI or web frontend is not required to prove the emulator architecture.

### 3. Separate hardware-oriented components

`CPU`, `Memory`, `FrameBuffer`, `Keypad`, `Timers`, `QuirkProfile`, and the host `Clock` are separate. `Machine` coordinates them.

### 4. Use one shared opcode decoder

The same immutable `Opcode` object provides nibble fields, validity checks, and mnemonics for execution, disassembly, debugging, tracing, and CFG analysis.

### 5. Bounds-check all memory access

Out-of-range instruction, sprite, BCD, and register-transfer access raises `MemoryAccessError`; addresses do not silently wrap through the 4 KB memory array.

### 6. Preserve the classic memory map

- memory: `0x000`–`0xFFF`
- built-in font: `0x050`
- ROM origin: `0x200`
- maximum ROM: 3584 bytes

Loading a shorter ROM at the same origin clears stale bytes left by a previous longer image.

### 7. Enforce CHIP-8 widths

Registers wrap to 8 bits. `I`, `PC`, return addresses, and relevant memory operations use 12-bit address semantics. The stack is limited to 16 levels.

### 8. Separate CPU speed from timer frequency

Instruction scheduling uses the requested speed. Delay and sound timers update independently at 60 Hz from elapsed clock time.

### 9. Inject time and randomness

`Machine.create()` accepts a clock and random seed. Headless execution defaults to seed `0` and uses a deterministic clock.

### 10. Use one framebuffer in all modes

Headless and interactive execution update the same 64×32 state. Terminal output is only an adapter that renders two CHIP-8 rows per terminal line with half-block characters.

### 11. Model historical behavior as named profiles

`classic` and `modern` profiles control:

- shift source (`VY` versus `VX`)
- whether logic operations reset `VF`
- whether `FX55`/`FX65` increment `I`
- sprite wrapping versus clipping

`BNNN` remains `NNN + V0` in both profiles.

### 12. Distinguish held keys from new key events

`EX9E`/`EXA1` inspect held state. `FX0A` requires a fresh completed press-and-release edge and discards stale buffered edges when waiting begins.

### 13. Make execution traces tamper-evident

`chip8-trace-v2` uses canonical JSON, a header-derived genesis hash, per-record SHA-256, sequence numbers, and previous-hash links. The header includes ROM identity and quirks.

### 14. Keep static analysis honest

The CFG reports unresolved edges for runtime-dependent `RET`, `BNNN`, blocking `FX0A`, and off-image targets rather than inventing certainty.

### 15. Run ROM validation in a subprocess

`test-rom` executes a deterministic headless child, captures stdout/stderr, enforces timeout, parses the final snapshot, checks optional golden values, and can verify the generated trace.

## Trade-offs Accepted

- Terminal rendering and input vary by host environment.
- Sound is a terminal bell transition, not sustained audio synthesis.
- Linear disassembly can label embedded data as code.
- Static CFG analysis cannot resolve dynamic control flow.
- `test-rom` proves crash-free execution and snapshot shape, not that a visual opcode suite declared success.
- Super-CHIP, XO-CHIP, save states, rewind, and graphical frontends are outside this version.

## Consequences

The emulator core is independently testable without a terminal. Headless runs are repeatable. Execution and analysis tools agree on decoding. Compatibility behavior is inspectable. ROM and trace identities are auditable. The architecture remains proportional to a portfolio capstone while still demonstrating genuine emulator engineering.

## Superseded By

None.

---

# Technical Design Document
## App — CPU Emulator
**Emulation Systems Group | Document 2 of 5**

---

## Purpose & Scope

CPU Emulator is a faithful CHIP-8 implementation with terminal play, deterministic headless execution, debugging and analysis tools, subprocess ROM validation, and hash-chained traces.

**Package:** `chip8-capstone`  
**Module:** `chip8`  
**Command:** `chip8`  
**Python:** 3.11+  
**Runtime dependencies:** none  
**Default quirks:** modern

## System Context

```text
ROM bytes
  ├── info / SHA-256
  ├── disassembler
  ├── CFG analyzer
  ├── subprocess test-rom
  └── Machine
        ├── host Clock
        └── CPU
              ├── Memory
              ├── FrameBuffer
              ├── Keypad
              ├── Timers
              ├── QuirkProfile
              └── RandomByte source
```

## Component Map

```text
src/chip8/
  cpu.py        fetch/decode/execute and CPU state
  opcode.py     instruction fields, validity, mnemonics
  memory.py     4 KB storage, font, ROM loading, bounds checks
  display.py    64×32 pixels and terminal rendering
  keyboard.py   logical keypad and terminal adapter
  timers.py     independent 60 Hz counters
  quirks.py     classic and modern policy profiles
  machine.py    deterministic/headless and interactive loops
  disasm.py     linear disassembly
  cfg.py        static control-flow graph
  trace.py      trace writing and verification
  runner.py     subprocess smoke-test orchestration
  cli.py        command interface and exit-code policy
  errors.py     public expected errors
```

## Machine State

### Memory

- `MEMORY_SIZE = 4096`
- `FONT_START = 0x050`
- `PROGRAM_START = 0x200`
- `read_word()` reads two bytes big-endian
- `load_rom()` rejects empty/oversized/overlapping images
- address and range operations are checked

### CPU

```text
V0..VF   sixteen 8-bit registers
I        12-bit index register
PC       12-bit program counter
stack    return addresses, maximum depth 16
cycles   retired instruction count
awaiting_key  FX0A blocking state
```

### Fetch Cycle

```text
address = PC
raw = memory.read_word(PC)
opcode = decode(raw)
PC = (PC + 2) & 0xFFF
execute(opcode, address)
cycles += 1
```

Unknown instructions raise `InvalidOpcodeError` with opcode and address.

## Opcode Representation

A 16-bit `Opcode` exposes:

```text
high = bits 15..12
x    = bits 11..8
y    = bits 7..4
n    = bits 3..0
nn   = bits 7..0
nnn  = bits 11..0
```

It also supplies `is_known` and `mnemonic()`. Exact low-byte/nibble checks disambiguate grouped instructions.

## Execution Semantics

### Control Flow

- `00E0`: clear display
- `00EE`: checked return
- `1NNN`: jump
- `2NNN`: checked call
- `3XNN`, `4XNN`, `5XY0`, `9XY0`: conditional skips
- `BNNN`: jump to `NNN + V0`

### Registers and Arithmetic

- `6XNN`: load byte
- `7XNN`: add immediate modulo 256
- `8XY0`: register copy
- `8XY1/2/3`: OR/AND/XOR
- `8XY4`: add with carry
- `8XY5`: subtract with no-borrow
- `8XY6`: right shift under quirk policy
- `8XY7`: reverse subtract
- `8XYE`: left shift under quirk policy
- `CXNN`: random byte AND mask

### Graphics

`DXYN` reads `N` sprite bytes from `I`, XORs set bits into the framebuffer, and stores collision in `VF`. The origin is reduced modulo screen dimensions. The sprite body wraps or clips according to the active profile.

### Input and Timers

- `EX9E`/`EXA1`: held-key tests
- `FX07`: read delay timer
- `FX0A`: wait for a new release edge
- `FX15`/`FX18`: set timers
- `FX1E`: add `VX` to `I`
- `FX29`: point `I` at font glyph

### Memory Operations

- `FX33`: binary-coded decimal at `I..I+2`
- `FX55`: store `V0..VX`
- `FX65`: load `V0..VX`
- post-operation `I` behavior follows the quirk profile

## Display

`FrameBuffer` stores a 32×64 integer matrix. Drawing XORs pixels and reports collision. Rendering uses Unicode half blocks:

```text
00 -> space
01 -> ▄
10 -> ▀
11 -> █
```

The `dirty` flag prevents unnecessary full redraws.

## Keyboard

`Keypad` stores:

- `pressed`: held keys
- `_released`: completed press/release events

`TerminalKeypad` requires a TTY. It uses `msvcrt` on Windows and `select`/`termios`/`tty` on Unix-like systems. Because terminals lack key-up events, it auto-releases after a short hold.

## Timers and Clocks

`Timers.update(now)` converts elapsed time to 60 Hz ticks and retains fractional remainder. `RealClock` uses `time.monotonic`; `DeterministicClock` advances only through `sleep()`.

## Machine Loops

### Headless

For a fixed number of cycles:

1. snapshot CPU state
2. update timers
3. execute one CPU cycle
4. append trace record if configured
5. advance deterministic time by `1 / speed`

### Interactive

The loop polls input, schedules instructions at the target speed, updates timers, redraws dirty pixels, updates a live status line, emits a bell when sound turns on, and optionally pauses after each step.

## Quirk Profiles

| Behavior | Classic | Modern |
|---|---|---|
| Shift source | `VY` | `VX` |
| Logic ops reset `VF` | yes | no |
| `FX55`/`FX65` increment `I` | yes | no |
| Sprite edges | wrap | clip |

## Disassembler

The linear sweep starts at `0x200`, decodes every two-byte word through the shared decoder, and emits an odd final byte as `.byte`. Embedded data may therefore be displayed as instructions.

## CFG Analyzer

Graph nodes are disassembled addresses. Edges model fallthrough, skips, direct jumps, and calls. DFS from `0x200` reports reachable and possible dead code. Dynamic and off-ROM transitions are recorded as unresolved.

## Trace System

Header fields:

- format (`chip8-trace-v2`)
- ROM SHA-256
- quirk profile

Records contain sequence, opcode address/value, before/after PC, cycles, registers, `I`, timers, stack, key-wait state, previous hash, and current hash.

Verification checks JSON schema/types, format version, chain links, record hashes, sequence, and optional exact ROM match.

## ROM Validation Runner

`validate_rom()` starts a new Python process running headless with seed `0`. It captures output, enforces timeout, extracts the final JSON snapshot, evaluates optional PC/cycle/register expectations, verifies an optional trace, and returns `ValidationReport`.

## Error Handling

Expected errors inherit from `Chip8Error`:

- `MemoryAccessError`
- `RomLoadError`
- `InvalidOpcodeError`
- `StackOverflowError`
- `StackUnderflowError`
- `TraceVerificationError`
- `InputUnavailableError`
- `InvalidKeyError`

## Known Limits

- CHIP-8 only
- terminal frontend and approximate sound
- no save states or rewind
- no cycle-accurate hardware electronics model
- static analysis may misclassify embedded data
- dynamic branches remain unresolved
- no keyboard events in headless mode

## Verification

The project uses strict mypy, Ruff, pytest strict mode, warnings-as-errors, a 30-second test timeout, and a 90% coverage gate. CI runs on Ubuntu and Windows for Python 3.11–3.14. The README reports about 99% coverage on 224 tests plus an optional external-ROM conformance skip.

---

# Interface Design Specification
## App — CPU Emulator
**Emulation Systems Group | Document 3 of 5**

---

## Invocation Syntax

```text
chip8 [--debug-errors] <command> ...
```

`--debug-errors` is accepted before or after the subcommand. `chip8 --version` prints the package version.

## Commands

### Run

```powershell
chip8 run ROM [--speed N] [--quirks classic|modern]
              [--step] [--headless] [--cycles N]
              [--seed N] [--trace PATH]
```

Rules:

- speed and cycles must be positive
- headless requires cycles
- step and headless cannot be combined
- interactive mode requires a TTY
- headless default seed is `0`
- step mode uses deterministic timer progression

Headless output includes ROM hash, profile, speed, seed, completion summary, and a final JSON CPU snapshot.

### Information

```powershell
chip8 info ROM
```

Prints path, byte size, load origin, SHA-256, first instructions, and odd-byte/unloadable warnings.

### Disassembly

```powershell
chip8 disasm ROM
```

Output shape:

```text
200: 00E0  CLS
202: 6101  LD V1, 0x01
```

Unknown instructions render as `.word 0xNNNN`; an odd trailing byte renders as `.byte`.

### Control-Flow Graph

```powershell
chip8 cfg ROM
```

Reports node counts, reachability, jump/call targets, possible dead code, malformed opcodes, unresolved edges, and adjacency.

### ROM Smoke Test

```powershell
chip8 test-rom ROM [--cycles N] [--timeout S]
                   [--quirks PROFILE] [--trace PATH]
                   [--report PATH] [--expect-pc VALUE]
                   [--expect-cycles N] [--expect-v0 VALUE ... --expect-vf VALUE]
```

Returns a JSON report. Exit `0` means the child completed and the final snapshot, optional golden values, and optional trace verification succeeded. Exit `1` means the smoke test failed.

### Trace Verification

```powershell
chip8 trace-verify TRACE [--rom ROM]
```

Verifies hash chain and optionally checks that the trace header's SHA-256 equals the supplied ROM's exact bytes.

## Argument Reference

| Option | Meaning |
|---|---|
| `--speed` | instructions per second, default 700 |
| `--quirks` | `classic` or `modern`, default modern |
| `--step` | pause after each interactive cycle |
| `--headless` | no terminal display or input |
| `--cycles` | positive execution budget |
| `--seed` | random source seed |
| `--trace` | trace output path |
| `--timeout` | subprocess test limit |
| `--report` | JSON validation report path |

## ROM Input Contract

- path must identify a file
- ROM cannot be empty
- executable image cannot exceed 3584 bytes
- load address is `0x200`
- larger files may still be disassembled/analyzed with a warning

## CPU Snapshot Contract

```json
{
  "pc": 512,
  "i": 0,
  "v": [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
  "stack": [],
  "delay_timer": 0,
  "sound_timer": 0,
  "cycles": 500,
  "awaiting_key": false
}
```

Optional snapshot fields include active quirks and a selected memory range.

## Exit Codes

| Code | Meaning |
|---:|---|
| 0 | success |
| 1 | `test-rom` failure |
| 2 | usage error or expected emulator failure |
| 70 | unexpected internal failure |
| 130 | Ctrl-C |

## Error Output

Expected failure:

```text
chip8: error: <message>
```

Unexpected failure:

```text
chip8: unexpected error: TypeName: message
```

With `--debug-errors`, exceptions are re-raised for a traceback.

## Library Interface

Primary exports:

```python
from chip8 import CPU, Machine, QuirkProfile, get_quirks
```

Deterministic example:

```python
from chip8 import Machine, get_quirks
from chip8.machine import DeterministicClock

machine = Machine.create(
    quirks=get_quirks("modern"),
    clock=DeterministicClock(),
    seed=0,
)
machine.cpu.load_rom(rom_bytes)
machine.run_headless(500)
state = machine.cpu.snapshot()
```

Additional useful interfaces include `Memory`, `FrameBuffer`, `Keypad`, `Timers`, `decode`, `disassemble`, `build_cfg`, `TraceWriter`, `verify_trace`, and `validate_rom`.

## Input Semantics

| Instruction | Key behavior |
|---|---|
| `EX9E` / `EXA1` | held-state query |
| `FX0A` | fresh press-and-release event |

Headless execution never polls the terminal. A ROM blocked on `FX0A` repeats that instruction until the cycle budget ends unless a programmatic keypad supplies an event.

## Side Effects

- interactive run changes terminal mode and emits ANSI/Unicode output
- run may ring the terminal bell
- trace creates parent directories and a file
- `test-rom` starts a subprocess and may write a trace/report
- `info` hashes exact ROM bytes

---

# Runbook
## App — CPU Emulator
**Emulation Systems Group | Document 4 of 5**

---

## Prerequisites

- Python 3.11+
- a real terminal for interactive play
- no third-party runtime packages

Development tooling includes pytest, pytest-cov, pytest-timeout, Ruff, and mypy.

## Installation

```powershell
python -m pip install .
```

Editable development install:

```powershell
python -m pip install -e ".[dev]"
```

Requirements-file alternative:

```powershell
python -m pip install -r requirements.txt
python -m pip install -r requirements-dev.txt
```

## Smoke Test

```powershell
chip8 --version
chip8 info tests/roms/increment-loop.ch8
chip8 disasm tests/roms/increment-loop.ch8
chip8 run tests/roms/increment-loop.ch8 --headless --cycles 20
```

A healthy headless run prints a completion line and final JSON snapshot.

## Deterministic Operations

Run:

```powershell
chip8 run rom.ch8 --headless --cycles 500 --seed 0 --quirks modern
```

Record and verify:

```powershell
chip8 run rom.ch8 --headless --cycles 500 --seed 0 --trace artifacts/trace.log
chip8 trace-verify artifacts/trace.log --rom rom.ch8
```

## Interactive Operations

```powershell
chip8 run game.ch8 --speed 700
```

Keyboard layout:

```text
1 2 3 4
Q W E R
A S D F
Z X C V
```

Stop with Ctrl+C.

## Step Debugger

```powershell
chip8 run rom.ch8 --step
```

The screen shows registers, stack, timers, framebuffer, and the current transition. Press Enter for the next instruction.

## Analysis

```powershell
chip8 disasm rom.ch8
chip8 cfg rom.ch8
```

Treat CFG unresolved entries as expected for returns, dynamic jumps, key waits, and targets outside the image.

## ROM Validation

Basic:

```powershell
chip8 test-rom rom.ch8 --cycles 500
```

Golden checks:

```powershell
chip8 test-rom rom.ch8 --cycles 500 --expect-pc 0x220 --expect-v0 0x2A
```

Artifacts:

```powershell
chip8 test-rom rom.ch8 --trace artifacts/trace.log --report artifacts/report.json
```

## Quirk Comparison

```powershell
chip8 run rom.ch8 --headless --cycles 500 --quirks modern
chip8 run rom.ch8 --headless --cycles 500 --quirks classic
```

Focus on shifts, logic flags, `FX55`/`FX65`, and edge sprites.

## Quality Checks

```powershell
pytest -q
ruff check src tests
mypy
```

Pytest configuration enforces coverage >=90%, warnings as errors, strict markers/configuration, and a 30-second timeout.

## CI Parity

GitHub Actions runs on Ubuntu and Windows for Python 3.11, 3.12, 3.13, and 3.14. Each job installs the editable package with dev dependencies, runs Ruff, strict mypy, and pytest. Coverage XML is retained from Ubuntu/Python 3.12.

## Optional Conformance

Windows:

```powershell
$env:CHIP8_CONFORMANCE_ROM_DIR="C:\path\to\roms"
pytest tests/conformance -q
```

Unix:

```bash
export CHIP8_CONFORMANCE_ROM_DIR=/path/to/roms
pytest tests/conformance -q
```

## Troubleshooting Tree

### Interactive input unavailable

**Symptom:** `interactive input requires a terminal`  
**Action:** run in Windows Terminal, Terminal.app, or another TTY. Use headless mode in automation.

### ROM cannot load

Check:

- file exists
- file is non-empty
- size is <=3584 bytes
- ROM targets CHIP-8 rather than an extended dialect

### Unsupported opcode

Use `chip8 disasm ROM` and inspect the reported address. Confirm the ROM does not require Super-CHIP/XO-CHIP.

### Stack overflow/underflow

Use step mode, trace, and CFG. Look for unmatched calls/returns or corrupted control flow.

### Headless run stalls on `FX0A`

This is expected because headless mode supplies no keyboard events. Use an interactive run or inject a `Keypad` in library tests.

### Trace verification fails

Check for edited, deleted, reordered, or truncated lines; a changed header; an old v1 trace; or the wrong ROM. Re-record with the current version.

### Windows display is incorrect

Use a modern Unicode/ANSI terminal. The application attempts to enable UTF-8 and virtual terminal processing, but legacy consoles can still render poorly.

## Recovery

The emulator does not persist mutable machine state between runs. Recovery generally means rerunning from the original ROM, chosen quirk profile, seed, and cycle budget. Verified traces provide evidence of the previous deterministic execution.

## Maintenance

- preserve one shared opcode decoder
- keep memory checks explicit
- keep timers independent of CPU speed
- keep headless defaults deterministic
- version trace format changes
- add tests before changing quirk semantics
- never describe `test-rom` as a complete conformance verdict
- write an ADR before adding extended CHIP-8 dialects, save states, or a graphical frontend

---

# Lessons Learned
## App — CPU Emulator
**Emulation Systems Group | Document 5 of 5**

---

## Summary

A CPU emulator is a boundary-management project. Host Python integers, clocks, terminals, random sources, and collections must not accidentally define the guest machine. The emulator succeeds when CHIP-8 behavior remains explicit, bounded, reproducible, and independently testable.

## Goals vs. Outcome

**Goal:** demonstrate a real instruction interpreter.  
**Outcome:** the project implements the documented CHIP-8 instruction groups, registers, checked stack, memory, display, keypad, and timers.

**Goal:** support reviewable debugging.  
**Outcome:** the same decoder drives disassembly, step output, traces, and CFG analysis.

**Goal:** make tests reliable.  
**Outcome:** injected time, input, display, and seeded randomness allow deterministic headless execution.

**Goal:** prove operational quality.  
**Outcome:** CLI exit codes, subprocess isolation, trace verification, CI matrices, strict typing, timeouts, and high coverage provide evidence beyond “it runs.”

## Decisions That Paid Off

### Hardware-oriented modules

Separating memory, CPU, display, keypad, timers, and host coordination made tests smaller and failure causes clearer.

### One decoder

A single `Opcode` representation prevents execution and analysis tools from disagreeing about nibble extraction or legal low-byte patterns.

### Deterministic headless mode

Seed `0` plus deterministic time makes snapshots and trace records reproducible across machines and CI runs.

### Named quirk profiles

Compatibility behavior is documented as policy rather than hidden conditionals.

### Hash-chained traces

The trace system turns an execution log into tamper-evident evidence tied to ROM bytes and quirk selection.

## Debt and Weaknesses

### Terminal frontend

It is sufficient for the capstone but host-dependent. A dedicated graphical/audio adapter would improve playability without changing the CPU core.

### Static analysis precision

Linear sweep cannot prove code versus embedded data. Dynamic control flow cannot always be resolved.

### Compatibility breadth

Two profiles cover major differences, not every historical interpreter. Extended CHIP-8 dialects are absent.

### Smoke-test interpretation

A subprocess run can prove that execution completed and matched golden state, but it cannot infer the visual pass/fail message of every third-party test ROM.

## Python Learnings

- Python's unlimited integers require explicit masking for 8-bit and 12-bit machine state.
- Dataclasses provide readable hardware-state containers without hiding mutation.
- Dependency injection is valuable even in a small emulator: clock, RNG, keypad, and display are test boundaries.
- `time.monotonic()` and fractional tick accumulation prevent timer drift from wall-clock changes.
- Platform-specific terminal input can be isolated behind one logical keypad interface.
- Canonical JSON and SHA-256 are enough to construct a clear educational hash chain.

## Architecture Insights

- Emulator correctness depends on separating guest semantics from host convenience.
- Timing domains should be modeled separately.
- Compatibility quirks deserve explicit names and documentation.
- Observability tools should reuse the same decoded representation as execution.
- Static tools should expose uncertainty instead of guessing.

## Testing Gaps

Manual validation still benefits from:

- IBM logo rendering
- a recognized public opcode suite
- a classic-quirks ROM
- a playable public-domain game
- terminal behavior across multiple hosts

Public ROM licensing prevents bundling all of these in CI.

## Reusable Patterns

- shared decoder model
- deterministic clock abstraction
- logical input interface with platform adapters
- structured CPU snapshots
- subprocess validation with timeout and report
- hash-chained JSON traces
- policy objects for historical behavior

## Rebuild Again

The next version would keep the CPU core and add:

1. trace replay and breakpoint debugger
2. configurable host keymap
3. dynamic coverage over the static CFG
4. a versioned save-state format
5. an optional graphical/audio frontend

## Questions for Future Work

- Should extended dialects share the current opcode model or use a versioned ISA layer?
- Can trace coverage improve code/data classification?
- What state is required for portable deterministic save states?
- How should RNG internal state be captured for exact resume?
- Which compatibility profiles provide meaningful coverage without becoming ROM-specific hacks?

---

*Constitution v2.0 checklist: fundamentals, explicit architecture, scope discipline, documented trade-offs, verification, and progressive complexity are all represented in this Core 5 package.*
