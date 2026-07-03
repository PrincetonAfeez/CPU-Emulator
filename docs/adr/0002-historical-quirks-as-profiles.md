# 0002 — Historical quirks as selectable profiles

Status: Accepted

## Context

CHIP-8 was implemented many times across the 1970s–90s, and real ROMs disagree
about several instructions. An interpreter must pick a behavior for each, and the
choice changes whether a given ROM runs correctly. The ambiguous cases this
project cares about are: the `8XY6`/`8XYE` shift source, whether `FX55`/`FX65`
increment `I`, whether `8XY1`/`8XY2`/`8XY3` reset `VF`, sprite edge handling in
`DXYN`, and the `BNNN` jump target.

## Decision

Model the choices as an explicit, immutable `QuirkProfile` (`src/chip8/quirks.py`)
with two named profiles selected by `--quirks`:

| Behavior | classic (COSMAC VIP) | modern (default) |
|---|---|---|
| `8XY6`/`8XYE` source | shift `VY` into `VX` | shift `VX` in place |
| `8XY1`/`8XY2`/`8XY3` | reset `VF` to 0 | leave `VF` unchanged |
| `FX55`/`FX65` | increment `I` | leave `I` unchanged |
| Sprite edges (`DXYN`) | wrap | clip (origin always wraps) |

`BNNN` is deliberately **not** profile-dependent: both profiles jump to
`NNN + V0`. The Super-CHIP `BXNN` variant was considered and rejected because it
reduces compatibility with the broad body of standard CHIP-8 ROMs, and keeping a
flag that no profile exercises would be dead code.

## Consequences

- The active profile is part of every state snapshot and trace header, so a run
  is self-describing and failures are easier to interpret.
- A ROM that depends on a specific quirk can be run under the matching profile.
- `DXYN` always reduces the sprite origin modulo the screen; only the body
  clips or wraps. This matches the common quirk-test expectation.
- Quirks beyond these (e.g. the `FX1E` overflow flag, `DXYN` vblank wait) are out
  of scope and intentionally unmodeled rather than half-implemented.
