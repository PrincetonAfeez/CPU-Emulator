# Schema

JSON Schema files for the CPU Emulator's structured output.

## Files

- `cpu-state.schema.json` — validates snapshots returned by `CPU.snapshot()`.
- `trace-header.schema.json` — validates the first JSON line in a trace file.
- `trace-record.schema.json` — validates each later JSON line in a trace file.
- `validation-report.schema.json` — validates `chip8 test-rom` JSON reports.

All schemas use JSON Schema Draft 2020-12.

## Notes

Trace files use JSON Lines rather than one JSON document. Validate line 1 with
`trace-header.schema.json`, then validate every remaining non-empty line with
`trace-record.schema.json`.

Place this `Schema` folder in the repository root beside `README.md` and
`pyproject.toml`.
