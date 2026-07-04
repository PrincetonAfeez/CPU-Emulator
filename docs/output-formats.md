# Structured analysis outputs

The disassembler and control-flow graph builder return deterministic Python
objects intended for programmatic use by tests, tools, and library callers.
This document is the compatibility contract for those structures.

## Compatibility

- **Field names and meanings** on `Instruction`, `Opcode`, and `CFG` are
  stable within the current major package version (`2.x`).
- **CLI text reports** (`format_disassembly()`, `CFG.format_report()`, and
  similar helpers) are human-readable only. Their exact wording, ordering, and
  formatting are **not** guaranteed as a machine-readable serialization format.
- Adding optional fields or new helper methods in a minor release is compatible;
  removing or renaming documented fields requires a major version bump.

## `disassemble(rom, start=0x200) -> list[Instruction]`

Linear sweep over ROM bytes, decoding every aligned two-byte word.

| Property | Type | Meaning |
|---|---|---|
| Return order | `list[Instruction]` | Ascending `address` (ROM load order) |
| `Instruction.address` | `int` | CHIP-8 address of the word (`start`, `start+2`, …) |
| `Instruction.opcode` | `Opcode` | Decoded 16-bit instruction |

**Odd trailing bytes:** when `len(rom)` is odd, the final byte is **not**
included in `disassemble()`. Use `format_disassembly()` to render it as a
`.byte` line after the last instruction.

## `Opcode`

Produced by `decode(value)` and stored on each `Instruction`.

| Member | Type | Meaning |
|---|---|---|
| `value` | `int` | Raw 16-bit opcode word (masked with `0xFFFF`) |
| `high` | `int` | Top nibble `(value >> 12) & 0xF` |
| `x` | `int` | Register X field `(value >> 8) & 0xF` |
| `y` | `int` | Register Y field `(value >> 4) & 0xF` |
| `n` | `int` | Low nibble `value & 0xF` |
| `nn` | `int` | Low byte `value & 0xFF` |
| `nnn` | `int` | Low 12 bits `value & 0xFFF` |
| `is_known` | `bool` | Whether the emulator recognizes and executes the word |
| `mnemonic()` | `str` | Assembly text for known opcodes; see below |
| `unknown()` | `str` | `.word 0xNNNN` placeholder for unrecognized words |

**`mnemonic()` behavior:**

- Known opcodes return the fixed mnemonic for their pattern (for example
  `LD V0, 0x01`, `CALL 0x206`).
- Unknown opcodes return `unknown()` (for example `.word 0x0000`).
- `is_known` is `False` exactly when `mnemonic()` would use the `.word` form
  for that value.

## `build_cfg(rom) -> CFG`

Static control-flow graph built from the ROM's linear disassembly.

| Field | Type | Meaning |
|---|---|---|
| `nodes` | `dict[int, Instruction]` | Instruction address → disassembled node |
| `edges` | `dict[int, set[int]]` | Source address → possible successor addresses |
| `unresolved` | `dict[int, str]` | Source address → explanation when targets depend on runtime state or lie outside the ROM image |
| `jump_targets` | `set[int]` | Direct `1NNN` jump targets |
| `call_targets` | `set[int]` | Direct `2NNN` call targets |
| `malformed` | `set[int]` | Node addresses whose opcode is not `is_known` |

**`reachable(start=0x200) -> set[int]`**

Depth-first walk from `start` following `edges`, staying within `nodes`.
Returns the set of reachable instruction addresses. Unknown start addresses or
addresses absent from `nodes` contribute nothing further.
