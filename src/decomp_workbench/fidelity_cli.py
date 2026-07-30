"""CLI for section-scoped instrumentation fidelity gates."""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from .fidelity import compare_object_fidelity


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
