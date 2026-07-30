"""CLI for the original/static pass differential adapter."""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from .pass_adapter import run_pass_differential


def pass_diff_command(args: argparse.Namespace) -> int:
    try:
        report = run_pass_differential(
            args.input,
            original_template=args.original_command,
            static_template=args.static_command,
            boundary=args.boundary,
            work_root=args.work_dir,
            compile_cwd=args.compile_cwd,
            timeout=args.timeout,
            stream_limit=args.stream_limit,
            downstream_template=args.downstream_command,
        )
    except (OSError, RuntimeError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        verdict = "IDENTICAL" if report["byte_identical"] else "DIFFERENT"
        normalized = "IDENTICAL" if report["normalized_identical"] else "DIFFERENT"
        print(
            f"pass boundary {report['boundary']}: bytes {verdict}, "
            f"host-normalized {normalized}"
        )
        if report["downstream"]:
            state = "IDENTICAL" if report["downstream"]["identical"] else "DIFFERENT"
            print(f"downstream: {state}")
        print(f"work directory: {report['work_directory']}")
        print(f"proof: {report['proof']}")
    if args.require_identical and not report["byte_identical"]:
        return 1
    return 0


def register_pass_adapter_command(
    commands: argparse._SubParsersAction[Any],
) -> None:
    parser = commands.add_parser(
        "pass-diff",
        help="compare a user-supplied original pass with a static recompilation",
        description=(
            "Run one retained pass boundary through explicit original and static "
            "commands, retain hashes and outputs in a project-visible directory, "
            "and optionally run the same downstream stage."
        ),
    )
    parser.add_argument("input")
    parser.add_argument("--original-command", required=True)
    parser.add_argument("--static-command", required=True)
    parser.add_argument("--downstream-command")
    parser.add_argument("--boundary", required=True)
    parser.add_argument(
        "--work-dir",
        default=".decomp-workbench/pass-diff",
        help="project-visible run root (default: .decomp-workbench/pass-diff)",
    )
    parser.add_argument(
        "--compile-cwd",
        default=".",
        help="working directory for every external pass",
    )
    parser.add_argument("--timeout", type=float, default=120.0)
    parser.add_argument("--stream-limit", type=int, default=64 * 1024)
    parser.add_argument("--require-identical", action="store_true")
    parser.add_argument("--json", action="store_true", help="emit JSON")
    parser.set_defaults(handler=pass_diff_command)
