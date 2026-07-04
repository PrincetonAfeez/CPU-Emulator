"""Command-line interface: run, disasm, info, cfg, test-rom, trace-verify."""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

from . import __version__
from .cfg import build_cfg
from .disasm import disassemble, format_disassembly
from .errors import Chip8Error, RomLoadError, TraceVerificationError
from .keyboard import TerminalKeypad
from .machine import DeterministicClock, Machine
from .memory import MEMORY_SIZE, PROGRAM_START
from .quirks import PROFILES, get_quirks
from .runner import validate_rom
from .trace import TraceWriter, read_header, sha256_bytes, verify_trace

logger = logging.getLogger("chip8")


def _configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="chip8: %(levelname)s: %(message)s",
        force=True,
    )


def build_parser() -> argparse.ArgumentParser:
    # A shared parent so --debug-errors is accepted both before and after the
    # subcommand (e.g. "chip8 --debug-errors run rom" or "chip8 run rom --debug-errors").
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--debug-errors", action="store_true", help="show Python tracebacks")

    parser = argparse.ArgumentParser(
        prog="chip8",
        description="CHIP-8 emulator and analysis tools",
        parents=[common],
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    subparsers = parser.add_subparsers(dest="command", required=True)

    run = subparsers.add_parser("run", parents=[common], help="run a ROM")
    run.add_argument("rom", type=Path)
    run.add_argument("--speed", type=_positive_int, default=700)
    run.add_argument("--quirks", choices=sorted(PROFILES), default="modern")
    run.add_argument("--step", action="store_true")
    run.add_argument("--headless", action="store_true")
    run.add_argument("--cycles", type=_positive_int)
    run.add_argument("--seed", type=int)
    run.add_argument("--trace", type=Path)

    disasm = subparsers.add_parser("disasm", parents=[common], help="disassemble a ROM")
    disasm.add_argument("rom", type=Path)

    info = subparsers.add_parser("info", parents=[common], help="show ROM identity and preview")
    info.add_argument("rom", type=Path)

    cfg = subparsers.add_parser("cfg", parents=[common], help="build a static control-flow graph")
    cfg.add_argument("rom", type=Path)

    test_rom = subparsers.add_parser(
        "test-rom",
        parents=[common],
        help="smoke-test a ROM in a subprocess (crash-free run + CPU snapshot)",
    )
    test_rom.add_argument("rom", type=Path)
    test_rom.add_argument("--cycles", type=_positive_int, default=500)
    test_rom.add_argument("--trace", type=Path, help="write a headless execution trace to PATH")
    test_rom.add_argument("--timeout", type=_positive_float, default=10.0)
    test_rom.add_argument("--quirks", choices=sorted(PROFILES), default="modern")
    test_rom.add_argument("--report", type=Path)
    test_rom.add_argument("--expect-pc", type=_int_literal, help="golden post-run PC")
    test_rom.add_argument("--expect-cycles", type=_positive_int, help="golden cycle count")
    for nibble in "0123456789abcdef":
        test_rom.add_argument(
            f"--expect-v{nibble}",
            type=_int_byte,
            help=f"golden V{nibble.upper()} value",
        )

    verify = subparsers.add_parser(
        "trace-verify", parents=[common], help="verify a hash-chained trace"
    )
    verify.add_argument("trace", type=Path)
    verify.add_argument("--rom", type=Path, help="cross-check the trace header against a ROM file")
    return parser


def _positive_int(value: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be greater than zero")
    return parsed


def _positive_float(value: str) -> float:
    parsed = float(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be greater than zero")
    return parsed


def _int_literal(value: str) -> int:
    parsed = int(value, 0)
    if parsed < 0 or parsed > 0xFFF:
        raise argparse.ArgumentTypeError("must be a CHIP-8 address or literal in 0..0xFFF")
    return parsed


def _int_byte(value: str) -> int:
    parsed = int(value, 0)
    if parsed < 0 or parsed > 0xFF:
        raise argparse.ArgumentTypeError("must be a byte value in 0..0xFF")
    return parsed


def _build_expect(args: argparse.Namespace) -> dict[str, object] | None:
    expect: dict[str, object] = {}
    if args.expect_pc is not None:
        expect["pc"] = args.expect_pc
    if args.expect_cycles is not None:
        expect["cycles"] = args.expect_cycles
    for nibble in "0123456789abcdef":
        value = getattr(args, f"expect_v{nibble}")
        if value is not None:
            expect[f"v{nibble}"] = value
    return expect or None


def _read_rom(path: Path) -> bytes:
    if not path.is_file():
        raise FileNotFoundError(f"ROM not found: {path}")
    rom = path.read_bytes()
    if not rom:
        raise RomLoadError("ROM is empty")
    return rom


MAX_ROM_SIZE = MEMORY_SIZE - PROGRAM_START


def _warn_if_unloadable(rom: bytes) -> None:
    if len(rom) > MAX_ROM_SIZE:
        logger.warning(
            "%s bytes exceeds the %s-byte CHIP-8 ROM limit at 0x%03X; "
            "this file could not be loaded to run",
            len(rom),
            MAX_ROM_SIZE,
            PROGRAM_START,
        )


def command_run(args: argparse.Namespace) -> int:
    rom = _read_rom(args.rom)
    _warn_if_unloadable(rom)
    interactive = not args.headless
    if args.headless and args.cycles is None:
        raise ValueError("--headless requires --cycles")
    if args.headless and args.step:
        raise ValueError("--step cannot be combined with --headless")
    if interactive and args.cycles is None:
        logger.info("interactive mode runs until Ctrl+C unless --cycles is set")
    keypad = TerminalKeypad() if interactive else None
    # Step mode also uses a deterministic clock so timers tick one instruction
    # period per step instead of racing down during the human pause between steps.
    clock = DeterministicClock() if (args.headless or args.step) else None
    # Headless mode is meant to be reproducible, so pin the RNG seed to 0 when
    # the user did not choose one. Interactive play stays nondeterministic.
    seed = args.seed
    if args.headless and seed is None:
        seed = 0
    if interactive and not args.step and args.seed is not None:
        logger.info(
            "--seed affects random opcodes only in interactive mode; "
            "timing and keyboard input remain nondeterministic"
        )
    machine = Machine.create(
        quirks=get_quirks(args.quirks), keypad=keypad, clock=clock, seed=seed
    )
    machine.cpu.load_rom(rom)
    trace_writer = (
        TraceWriter.open(args.trace, rom=rom, quirks=machine.cpu.quirks.describe())
        if args.trace
        else None
    )
    try:
        print(
            f"ROM SHA-256: {sha256_bytes(rom)}\n"
            f"Quirk profile: {args.quirks}\n"
            f"CPU speed: {args.speed} instructions/s"
        )
        if seed is not None:
            print(f"Random seed: {seed}")
        if args.headless:
            machine.run_headless(args.cycles, speed=args.speed, trace=trace_writer)
            print(
                f"Completed {machine.cpu.cycles} cycles; PC=0x{machine.cpu.pc:03X}; "
                f"lit pixels={machine.cpu.display.lit_pixels()}"
            )
            print(json.dumps(machine.cpu.snapshot(), sort_keys=True))
        else:
            machine.run_interactive(
                speed=args.speed,
                max_cycles=args.cycles,
                step_mode=args.step,
                trace=trace_writer,
            )
            print(
                f"Completed {machine.cpu.cycles} cycles; PC=0x{machine.cpu.pc:03X}; "
                f"lit pixels={machine.cpu.display.lit_pixels()}"
            )
    finally:
        if trace_writer is not None:
            trace_writer.close()
    return 0


def command_info(args: argparse.Namespace) -> int:
    rom = _read_rom(args.rom)
    _warn_if_unloadable(rom)
    print(f"File: {args.rom}")
    print(f"Size: {len(rom)} bytes")
    print(f"Load address: 0x{PROGRAM_START:03X}")
    print(f"SHA-256: {sha256_bytes(rom)}")
    print("First instructions:")
    for instruction in disassemble(rom)[:10]:
        print(f"  {instruction.format()}")
    if len(rom) % 2:
        logger.warning("ROM has an odd trailing byte")
    return 0


def command_test_rom(args: argparse.Namespace) -> int:
    rom = _read_rom(args.rom)
    _warn_if_unloadable(rom)
    report = validate_rom(
        args.rom,
        cycles=args.cycles,
        timeout=args.timeout,
        quirks=args.quirks,
        trace=args.trace,
        expect=_build_expect(args),
    )
    output = report.to_json()
    print(output)
    if report.failure_reason:
        logger.error("test-rom failed: %s", report.failure_reason)
    if args.report:
        args.report.write_text(output + "\n", encoding="utf-8")
    return 0 if report.success else 1


def dispatch(args: argparse.Namespace) -> int:
    if args.command == "run":
        return command_run(args)
    if args.command == "disasm":
        rom = _read_rom(args.rom)
        _warn_if_unloadable(rom)
        print(format_disassembly(rom))
        return 0
    if args.command == "info":
        return command_info(args)
    if args.command == "cfg":
        rom = _read_rom(args.rom)
        _warn_if_unloadable(rom)
        print(build_cfg(rom).format_report())
        return 0
    if args.command == "test-rom":
        return command_test_rom(args)
    if args.command == "trace-verify":
        count, final_hash = verify_trace(args.trace)
        print(f"Trace verified: {count} records; final hash={final_hash}")
        if args.rom is not None:
            expected = sha256_bytes(_read_rom(args.rom))
            recorded = read_header(args.trace).get("rom_sha256")
            if recorded != expected:
                raise TraceVerificationError(
                    f"ROM mismatch: {args.rom} hashes to {expected}, "
                    f"but the trace header records {recorded}"
                )
            print(f"ROM match: {args.rom} matches the trace (SHA-256 {expected})")
        return 0
    raise AssertionError("argparse accepted an unknown command")


def main(argv: list[str] | None = None) -> int:
    _configure_logging()
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return dispatch(args)
    except KeyboardInterrupt:
        # Ctrl-C is a normal way to stop an interactive run; exit cleanly with
        # the conventional 128 + SIGINT status instead of dumping a traceback.
        logger.error("interrupted")
        return 130
    except (Chip8Error, OSError, ValueError) as exc:
        if args.debug_errors:
            raise
        logger.error("%s", exc)
        return 1
    except Exception as exc:
        # Last resort: surface a clean message instead of a raw traceback unless
        # the user opted into --debug-errors.
        if args.debug_errors:
            raise
        logger.error("unexpected error: %s: %s", type(exc).__name__, exc)
        return 70

