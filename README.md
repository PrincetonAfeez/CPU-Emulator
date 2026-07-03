# CHIP-8 CPU Emulator

[![CI](https://img.shields.io/badge/CI-GitHub%20Actions-2088FF?logo=githubactions&logoColor=white)](.github/workflows/ci.yml)
![Coverage](https://img.shields.io/badge/coverage-99%25-brightgreen)
![Python](https://img.shields.io/badge/python-3.11%2B-blue)
![Version](https://img.shields.io/badge/version-1.0.2-blue)

A complete, CLI-first CHIP-8 virtual machine written in Python. It runs ROMs in
the terminal, supports deterministic headless execution, and includes a shared
disassembler, step debugger, static control-flow graph analyzer, subprocess ROM
validator, ROM identity hashes, and tamper-evident execution traces.

## Install and run

```console
python -m pip install .
# or editable with dev tools:
python -m pip install -e ".[dev]"
# or via requirements files:
python -m pip install -r requirements.txt
python -m pip install -r requirements-dev.txt
chip8 info path/to/rom.ch8
chip8 disasm path/to/rom.ch8
chip8 run path/to/rom.ch8 --speed 700
chip8 run path/to/rom.ch8 --step
chip8 run path/to/rom.ch8 --headless --cycles 500 --seed 0 --trace trace.log
chip8 trace-verify trace.log --rom path/to/rom.ch8
chip8 cfg path/to/rom.ch8
chip8 test-rom path/to/rom.ch8 --cycles 500
```

Headless runs default the RNG seed to `0` so they are reproducible; pass
`--seed N` to vary it. In interactive mode, `--seed` affects `CXNN` randomness
only — wall-clock and keyboard timing stay nondeterministic (a note is printed
if you pass `--seed` without `--headless` or `--step`). `trace-verify --rom`
additionally confirms the trace was produced from that exact ROM file.

Run the test suite with `pytest`, lint with `ruff check src tests`, and
type-check with `mypy` (configured for `--strict`). Print the version with
`chip8 --version`.

## Development

```console
python -m pip install -e ".[dev]"
pytest -q
ruff check src tests
mypy
```

CI runs the same checks on Ubuntu and Windows across Python 3.11–3.14 (see
[`.github/workflows/ci.yml`](.github/workflows/ci.yml)). Coverage must stay at
or above 90% (`--cov-fail-under=90`); the current suite is ~99% on 224 tests
(plus one optional conformance skip when `CHIP8_CONFORMANCE_ROM_DIR` is unset).
Each test has a 30s timeout via `pytest-timeout`.

## CLI behavior

Add `--debug-errors` (before or after the subcommand) to see full Python
tracebacks instead of the friendly one-line messages. Files larger than a
loadable ROM (3584 bytes) still disassemble, but `info`, `disasm`, `cfg`, and
`run` print a warning that the file could not be loaded to run.

Interactive `chip8 run` requires a real terminal (stdin must be a TTY). Piped or
redirected stdin exits with code 2 and a friendly error message. Without
`--cycles`, interactive mode runs until you press Ctrl+C (a note is printed).

Headless mode never polls keyboard input. A ROM that blocks on `FX0A` will spin
until `--cycles` is exhausted; `test-rom` timeouts on such ROMs report whether
the CPU was waiting for a key when a snapshot was available.

Exit codes:

| Code | Meaning |
|---|---|
| 0 | success |
| 1 | `test-rom` smoke test failed (crash, timeout, golden mismatch, or trace verify failure) |
| 2 | usage error, or a reported emulator error (missing/oversized ROM, invalid opcode, stack over/underflow, trace mismatch) |
| 70 | unexpected internal error (re-run with `--debug-errors` for the traceback) |
| 130 | interrupted with Ctrl-C |

## Machine model

CHIP-8 has 4096 bytes of memory addressed from `0x000` through `0xFFF`. This
emulator places the built-in 4×5 hexadecimal font at `0x050` and loads programs
at `0x200`. A ROM can therefore occupy at most 3584 bytes. Bounds are checked for
instruction, sprite, and data access; out-of-range addresses raise
`MemoryAccessError` rather than wrapping silently.

The CPU has sixteen 8-bit registers, `V0` through `VF`; arithmetic wraps modulo
256. `VF` doubles as the carry, no-borrow, shift, and sprite-collision flag. `I`
is a 12-bit index register (masked to `0xFFF` for memory operations), `PC` is
the program counter (also masked to `0xFFF`, including on `RET`), and a checked
16-level stack stores subroutine return addresses. Delay and sound timers are
8-bit values that count down independently at 60 Hz.

Reloading a shorter ROM clears any tail bytes left by a previously loaded longer
program at `0x200`.

During fetch, the CPU reads two bytes at `PC` in big-endian order and advances
`PC` by two. Decode extracts the high nibble, X, Y, N, NN, and NNN fields with
masks and shifts. The exact low byte or low nibble disambiguates the shared
`0x0`, `0x8`, `0xE`, and `0xF` groups. Execution then changes registers, memory,
display, or control flow. The same `Opcode` object supplies execution,
disassembly, tracing, debugging, and CFG analysis, preventing five subtly
different decoders.

## Display and input

The framebuffer is a 64×32 matrix. `DXYN` reads N sprite bytes at `I`; each set
bit XORs one display pixel. The draw position is first reduced modulo the screen
size, and the sprite body then wraps or clips at the edges according to the
active quirk. Erasing an already-lit pixel sets `VF`; a zero-height sprite
(`DXY0`) draws nothing and clears `VF`. The terminal renderer
combines two CHIP-8 rows into Unicode half-block characters (upper half for a lit
top pixel, lower half for a lit bottom pixel), while headless mode updates the
same framebuffer without terminal output. On Windows the renderer enables UTF-8
output and virtual-terminal processing so the block glyphs and ANSI cursor codes
display correctly.

The classic keyboard mapping is:

```text
Host       CHIP-8
1 2 3 4    1 2 3 C
Q W E R    4 5 6 D
A S D F    7 8 9 E
Z X C V    A 0 B F
```

Windows uses `msvcrt`; Unix-like terminals use `select`, `termios`, and `tty`.
Those details live in `TerminalKeypad`. The CPU only sees a small keypad
interface, so tests can press and release virtual keys directly.

`FX0A` (wait for key) requires a completed press-then-release edge, not merely a
held key. This avoids satisfying a wait with stale input buffered from earlier
play; `TerminalKeypad` auto-releases keys after a short hold because terminals
do not report key-up events.

| Instruction | Input semantics |
|---|---|
| `EX9E` / `EXA1` (skip if key down/up) | Key is **held** (`is_pressed`) |
| `FX0A` (wait for key) | Key must be **pressed and released** (edge) |

Sound output is approximate: the terminal emits a single bell when the sound
timer transitions from 0 to non-zero, rather than a sustained tone for the full
timer duration.

## Timing and architecture

CPU speed and timer speed are separate. The host loop schedules instructions at
the requested `--speed`, while elapsed clock time is converted to independent
60 Hz timer ticks. An injected deterministic clock advances exactly one CPU
period per headless cycle. Random bytes, clocks, display, and keypad state are
also injected, which keeps CPU tests deterministic and free of terminal setup.

The modules follow the hardware boundary: memory owns bytes and bounds checks;
CPU owns fetch/decode/execute state; display owns pixels; keyboard adapts host
input; timers own 60 Hz countdown state; `Machine` coordinates those parts. The
non-obvious decisions behind this layout are recorded as ADRs in
[`docs/adr/`](docs/adr/).

## Historical quirks

CHIP-8 behavior changed across interpreters. Select a profile with
`--quirks classic` or `--quirks modern`.

| Behavior | classic | modern (default) |
|---|---|---|
| `8XY6`/`8XYE` source | shift `VY` into `VX` | shift `VX` in place |
| `8XY1`/`8XY2`/`8XY3` | reset `VF` to 0 | leave `VF` unchanged |
| `FX55`/`FX65` | increment `I` afterward | leave `I` unchanged |
| Sprite edges | wrap | clip |

`BNNN` is intentionally not profile-dependent: both profiles jump to `NNN + V0`,
the COSMAC/standard behavior and the most ROM-compatible choice. The active
profile appears in run output, state snapshots, and trace headers.

## Debugging and analysis

Step mode prints the current instruction, registers, stack, timers, and
framebuffer after each cycle. Structured CPU snapshots expose the same state to
tests and tools.

The CFG analyzer first disassembles every two-byte word into a graph node.
Ordinary instructions add a fallthrough edge, skips add both possible edges,
direct jumps add their target, and calls add target plus return-site
fallthrough. Depth-first search from `0x200` identifies reachable and possible
dead code. `BNNN`, `RET`, and blocking `FX0A` remain honestly unresolved because
their targets or fallthrough depend on runtime state.

`test-rom` is a **smoke test**: it starts a separate Python process, captures
stdout, stderr, and exit status, applies a timeout, fixes the random seed, and
parses the final CPU snapshot from headless output. It confirms the ROM runs
without crashing and produces a well-formed snapshot; it does not verify opcode
test-suite pass/fail. Optional golden checks: `--expect-pc`, `--expect-cycles`,
and `--expect-v0` through `--expect-vf`. Failed runs print a one-line reason on
stderr and include `failure_reason` / `mismatch_details` in the JSON report.
Optional `--trace PATH` writes and verifies a trace file (parent directories are
created as needed). Optional `--report` writes a JSON summary.

`info` hashes the exact ROM bytes with SHA-256. Trace files use format
`chip8-trace-v2` (`chip8-trace-v1` is rejected; re-record old logs). Each record
contains the instruction address, `before_pc`,
post-instruction `after_pc`, `cycles`, registers, timers, stack, `awaiting_key`,
the previous record hash, then hashes its canonical JSON. Changing a record
breaks its own hash or the following link, so `trace-verify` detects tampering.

## Validation

The included **224 automated tests** cover opcode field extraction, flow control,
arithmetic and flags, shifts under both profiles, random masking, drawing and
collision, keyboard skips and wait-for-key, timers, BCD, register transfers,
disassembly, CFG reachability, trace tampering, deterministic machine execution,
CLI subprocess behavior, and bundled smoke-test ROMs at
`tests/roms/increment-loop.ch8`, `tests/roms/opcode-smoke.ch8`, and
`tests/roms/classic-fx55.ch8`. Public ROMs are intentionally not redistributed;
use the commands above with an IBM logo ROM, a recognized CHIP-8 opcode test
ROM, and a public-domain game to complete visual and interactive validation.

### Manual acceptance checklist

These capstone checks require your own ROM files and are not automated in CI:

| Check | Command / action | Pass criterion |
|---|---|---|
| IBM logo | `chip8 run ibm-logo.ch8` | Logo renders correctly in the terminal |
| Opcode suite | Run a recognized opcode test ROM under `--quirks modern` | Test output indicates pass, or document intentional quirk differences |
| Quirks | Run a flags/quirks test ROM under `--quirks classic` | Behavior matches the classic profile |
| Playability | `chip8 run` a public-domain game interactively | Game is playable with the documented key map |
| Trace integrity | `chip8 run rom.ch8 --headless --cycles N --trace t.log` then `chip8 trace-verify t.log --rom rom.ch8` | Verification succeeds |

Optional conformance tests against your own opcode-test ROM collection are
available when `CHIP8_CONFORMANCE_ROM_DIR` points at a directory of `.ch8` files:

```console
set CHIP8_CONFORMANCE_ROM_DIR=C:\path\to\roms   # Windows
export CHIP8_CONFORMANCE_ROM_DIR=/path/to/roms  # Unix
pytest tests/conformance -q
```

Linear disassembly and CFG analysis treat ROM bytes as sequential code; embedded
data may be mislabeled. This is a documented limitation, not a decoder bug.

## License

MIT — see [`LICENSE`](LICENSE). Copyright (c) 2026 Princeton Afeez.
