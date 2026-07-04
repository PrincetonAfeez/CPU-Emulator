# Test ROMs

Public CHIP-8 test ROMs are intentionally **not** redistributed in this
repository. To run the visual and interactive acceptance checks, drop ROM files
here and point the CLI at them, for example:

```console
chip8 info tests/roms/ibm-logo.ch8
chip8 run tests/roms/ibm-logo.ch8 --headless --cycles 200
chip8 run tests/roms/corax-opcode-test.ch8
chip8 cfg tests/roms/ibm-logo.ch8
```

Recommended public-domain ROMs for validation:

- the IBM logo ROM (first visual milestone)
- a recognized CHIP-8 opcode test ROM (e.g. Corax/Timendus)
- a flags/quirks test ROM
- any public-domain game (e.g. Pong, Brix) for interactive play

The automated unit and integration tests in `tests/unit` and
`tests/integration` use tiny hand-assembled ROMs, so the suite stays fully
self-contained and passes without any files in this directory.

## Bundled smoke-test ROMs

`increment-loop.ch8` — sets `V0` to 1, increments each cycle, and jumps back.
After 5 headless cycles the snapshot should read `V0=3`, `PC=0x202`.

`opcode-smoke.ch8` — `LD V0, 3` then `ADD`/`JP` loop. After 3 cycles: `V0=4`,
`PC=0x202`.

`classic-fx55.ch8` — stores `V0`/`V1` with classic-profile `FX55`, which
increments `I`. After 4 headless cycles under `--quirks classic`: `I=0x302`,
memory at `0x300..0x301` is `01 02`. All three run on every CI build.
