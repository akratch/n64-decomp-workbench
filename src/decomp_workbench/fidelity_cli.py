"""CLI for section-scoped instrumentation fidelity gates."""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from .fidelity import compare_object_fidelity
from .instrument_gate import (
    InstrumentGateError,
    build_stamp,
    gate_lines,
    verification_lines,
    verify_stamp,
    write_stamp,
)
from .terminal import add_terminal_arguments, emit_lines


def fidelity_command(args: argparse.Namespace) -> int:
    try:
        report = compare_object_fidelity(
            args.stock,
            args.instrumented,
            objdump=args.objdump,
            sections=tuple(args.section),
            timeout=args.timeout,
        )
    except (OSError, RuntimeError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        state = "PASS" if report["pass"] else "FAIL"
        print(f"object fidelity: {state}")
        for gate, passed in report["gates"].items():
            print(f"{gate}: {'PASS' if passed else 'FAIL'}")
        if report["pass"] and not report["file_identical"]:
            print("note: scoped sections agree; whole-file metadata differs")
        print(f"proof: {report['proof']}")
    return 0 if report["pass"] else 1


def register_fidelity_command(
    commands: argparse._SubParsersAction[Any],
) -> None:
    parser = commands.add_parser(
        "fidelity",
        help="gate instrumentation on sections, relocations, and symbols",
    )
    parser.add_argument("stock")
    parser.add_argument("instrumented")
    parser.add_argument("--objdump")
    parser.add_argument(
        "--section",
        action="append",
        default=[".text", ".rodata", ".data"],
        help="content section to gate; repeatable",
    )
    parser.add_argument("--timeout", type=float, default=10.0)
    parser.add_argument("--json", action="store_true", help="emit JSON")
    parser.set_defaults(handler=fidelity_command)


def instrument_gate_command(args: argparse.Namespace) -> int:
    try:
        if args.verify:
            result = verify_stamp(
                args.verify, objdump=args.objdump, timeout=args.timeout
            )
            if args.json:
                print(json.dumps(result, indent=2, sort_keys=True))
            else:
                emit_lines(
                    verification_lines(result), width=args.width, pager=args.pager
                )
            return 0 if result["pass"] else 1
        if not (args.stock and args.instrumented):
            raise InstrumentGateError(
                "pass --stock OBJ --instrumented OBJ (two objects built from "
                "one source by the stock and instrumented toolchains), or "
                "--verify STAMP to re-run a recorded gate"
            )
        stamp = build_stamp(
            stock=args.stock,
            instrumented=args.instrumented,
            profile=args.profile,
            objdump=args.objdump,
            sections=tuple(args.section),
            timeout=args.timeout,
            note=args.note or "",
        )
        written = write_stamp(stamp, path=args.stamp) if args.stamp else None
    except (InstrumentGateError, OSError, RuntimeError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    if args.json:
        payload = dict(stamp)
        if written is not None:
            payload["stamp_path"] = str(written)
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        emit_lines(
            gate_lines(stamp, stamp_path=written), width=args.width, pager=args.pager
        )
    return 0 if stamp["pass"] else 1


_GATE_DESCRIPTION = (
    "Prove an instrumented toolchain reproduces the stock object, and record "
    "that it did. With tracing off, an instrumented pass must emit the same "
    ".text, .rodata, .data, relocations and symbol table as the stock pass; "
    "otherwise its traces describe a compiler nobody is trying to match. One "
    "campaign honoured that requirement by hand, every time, and left no "
    "record -- twelve instruments across four passes, and the only evidence "
    "any of them was gated was a stage's own sentence. This runs the "
    "section-scoped comparison and writes a stamp naming the profile, both "
    "objects and their hashes, and exactly what the gate does and does not "
    "claim. --verify re-runs it rather than trusting the record. The "
    "workbench does not build compilers; both objects come from the project's "
    "own build."
)


def register_instrument_gate_command(
    commands: argparse._SubParsersAction[Any],
) -> None:
    parser = commands.add_parser(
        "instrument-gate",
        help="gate an instrumented toolchain against stock, and stamp it",
        description=_GATE_DESCRIPTION,
        epilog=(
            "example: decomp-workbench instrument gate --stock stock.o "
            "--instrumented cdx.o --profile uopt-cdx --stamp gates/uopt-cdx.json"
        ),
    )
    parser.add_argument(
        "--stock", metavar="OBJ", help="object from the stock toolchain"
    )
    parser.add_argument(
        "--instrumented",
        metavar="OBJ",
        help="object from the instrumented toolchain, tracing off",
    )
    parser.add_argument(
        "--profile",
        default="",
        metavar="NAME",
        help="which instrumented pass this stamp is about, e.g. uopt-cdx",
    )
    parser.add_argument(
        "--stamp",
        metavar="FILE",
        help="write the gate record here (the directory must already exist)",
    )
    parser.add_argument(
        "--verify",
        metavar="FILE",
        help="re-run the gate a stamp records and report what changed",
    )
    parser.add_argument("--note", help="one line about how the objects were built")
    parser.add_argument("--objdump")
    parser.add_argument(
        "--section",
        action="append",
        default=[".text", ".rodata", ".data"],
        help="content section to gate; repeatable",
    )
    parser.add_argument("--timeout", type=float, default=10.0)
    parser.add_argument("--json", action="store_true", help="emit JSON")
    add_terminal_arguments(parser)
    parser.set_defaults(
        handler=instrument_gate_command, report_command="instrument-gate"
    )
