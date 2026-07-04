# Changelog

All notable changes to this project are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.3] — 2026-07-03

### Changed
- CLI exit codes now distinguish argparse usage errors from expected
  runtime/emulator failures.
- Expected runtime/emulator failures now return 1.
- argparse command-line usage errors remain 2.
- CLI diagnostics (warnings, notes, and errors) now use the `logging` module
  instead of direct `print(..., file=sys.stderr)`.
- PyPI development-status classifier updated from Production/Stable to Beta.
- Development dependencies are pinned in `requirements-dev.lock`; CI installs
  from the lockfile.

### Fixed
- Trace validation now reports malformed valid-JSON inputs as
  `TraceVerificationError` instead of unexpected internal errors.
- Trace header validation now requires and type-checks ROM hash and quirk
  metadata.
- Trace record validation rejects JSON booleans in integer fields and enforces
  CHIP-8 address, byte, and hex-digest ranges.

### Documentation
- Documented structured disassembly and CFG outputs in `docs/output-formats.md`.
- ADR 0003 and README updated for full trace schema validation and CLI exit
  codes.

## [1.0.2] — 2026-06-26

### Changed
- Synchronized package version across `pyproject.toml`, `chip8.__version__`, and docs
- CI: pip caching, `ruff` on `src` and `tests`, coverage XML artifact, concurrency control
- Raised `--cov-fail-under` to 90% (current suite: ~99%)
- Added `requirements.txt` and `requirements-dev.txt` for non-PEP-517 installs

### Tests
- Expanded to 224 automated tests with per-module unit coverage
- Parametrized tests for all standard opcodes and trace schema validation
- Global 30s per-test timeout via `pytest-timeout`

## [1.0.1] — 2026-06-19

### CLI and validation
- `test-rom` reports `failure_reason` and `mismatch_details` for golden snapshot failures
- Golden flags: `--expect-v0` through `--expect-vf`; trace output is verified automatically
- Empty ROMs rejected consistently across `run`, `disasm`, `cfg`, and `info`
- Interactive mode notes when it will run until Ctrl+C; headless `FX0A` blocking documented

### Trace and input
- `chip8-trace-v1` rejected with an explicit upgrade message; header-only traces rejected
- Blank lines skipped during verification; trace paths create parent directories
- `Keypad.release()` validates key range like `press()`

### Tests and docs
- Bundled `classic-fx55.ch8` smoke ROM for classic-profile `FX55` behavior
- README development section, manual acceptance checklist, and CI workflow badge
- Boundary tests for `FX33` / `FX65`; Windows Ctrl+C keyboard test

## [1.0.0] — 2026-06-19

### Added
- Complete CHIP-8 CPU with classic/modern quirk profiles
- Strict 12-bit address model with bounds-checked memory (ADR-0004)
- CLI: `run`, `info`, `disasm`, `cfg`, `test-rom`, `trace-verify`
- Headless deterministic runs with hash-chained traces (`chip8-trace-v2`)
- ROM reload tail clearing; overlapping loads rejected
- Bundled smoke ROMs: `increment-loop.ch8`, `opcode-smoke.ch8`
- CI on Ubuntu and Windows (Python 3.11–3.14)

[1.0.3]: https://github.com/example/chip8-capstone/compare/v1.0.2...v1.0.3
[1.0.2]: https://github.com/example/chip8-capstone/compare/v1.0.1...v1.0.2
[1.0.1]: https://github.com/example/chip8-capstone/compare/v1.0.0...v1.0.1
[1.0.0]: https://github.com/example/chip8-capstone/releases/tag/v1.0.0
