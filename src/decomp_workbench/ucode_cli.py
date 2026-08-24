"""CLI for retained IDO binary Ucode switch dispatches."""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from .ucode import build_ucode_xjp_report


def ucode_xjp_command(args: argparse.Namespace) -> int:
    try:
        report = build_ucode_xjp_report(
            args.stream, expression_limit=args.expression_limit
        )
    except (OSError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0

    stream = report["stream"]
    print(
        f"Ucode: {stream['record_count']} record(s), {stream['bytes']} bytes, "
        f"sha256={stream['sha256'][:12]}"
    )
    print(f"XJP dispatches: {report['dispatch_count']}")
    for number, dispatch in enumerate(report["dispatches"], start=1):
        xjp = dispatch["xjp"]
        print(
            f"XJP {number}: {xjp['offset_hex']} {xjp['dtype_name']} "
            f"range={dispatch['lower_bound']}..{dispatch['upper_bound']} "
            f"cases=L{dispatch['case_table_label']} "
            f"default=L{dispatch['default_label']}"
        )
        completeness = (
            "complete" if dispatch["selector_expression_complete"] else "partial"
        )
        print(f"  selector ({completeness} postfix slice):")
        for record in dispatch["selector_expression"]:
            print(
                f"    {record['offset_hex']:>8s} {record['name']:<6s} "
                f"{record['detail']}"
            )
        targets = dispatch["case_targets"]
        table_status = "complete" if dispatch["case_table_complete"] else "partial"
        if targets:
            print(f"  table ({table_status}, {len(targets)} entries):")
            cases = dispatch["cases"]
            for start in range(0, len(cases), 8):
                rendered = ", ".join(
                    f"{case['value']}->"
                    + "->".join(
                        f"L{label}" for label in case["target_chain"]["labels"]
                    )
                    for case in cases[start : start + 8]
                )
                print(f"    {rendered}")
            if dispatch["trampoline_case_count"]:
                print(
                    "  trampoline targets: "
                    f"{dispatch['trampoline_case_count']}/{len(cases)}"
                )
        else:
            print("  table: not resolved immediately after XJP")
    print(f"proof: {report['proof']}")
    return 0


def register_ucode_command(
    commands: argparse._SubParsersAction[Any],
) -> None:
    parser = commands.add_parser(
        "inspect-ucode",
        help="inspect retained IDO binary Ucode XJP dispatches",
        description=(
            "Statically decode a big-endian IDO binary Ucode stream and report "
            "every XJP selector expression, case-table/default labels, range, "
            "dense Uclab/Uujp table, and metadata-only jump-trampoline chains. "
            "This command does not run a compiler."
        ),
    )
    parser.add_argument(
        "stream",
        help="retained IDO binary Ucode input (UGEN positional input, not -temp)",
    )
    parser.add_argument(
        "--expression-limit",
        type=int,
        default=64,
        help="maximum records searched backward for each selector (default: 64)",
    )
    parser.add_argument("--json", action="store_true", help="emit JSON")
    parser.set_defaults(handler=ucode_xjp_command)
