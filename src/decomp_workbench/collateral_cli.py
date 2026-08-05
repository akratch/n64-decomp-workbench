"""CLI for translation-unit collateral reporting."""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from .collateral import DEFAULT_IGNORES, compare_object_collateral


def collateral_command(args: argparse.Namespace) -> int:
    try:
        report = compare_object_collateral(
            args.reference,
            args.candidate,
            symbol=args.symbol,
            section=args.section,
            objdump=args.objdump,
            ignore=tuple(args.ignore_section),
            timeout=args.timeout,
        )
    except (OSError, RuntimeError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        state = "DETECTED" if report["collateral_detected"] else "NONE"
        print(f"object collateral: {state} classification={report['classification']}")
        if report["selected_symbol"] is not None:
            exact = "yes" if report["selected_function_exact"] else "no"
            print(
                f"selected function: {report['selected_symbol']} "
                f"raw/relocation exact={exact}"
            )
        for item in report["section_changes"]:
            print(
                f"{item['section']}: size-delta={item['size_delta']:+d} "
                f"changed={','.join(item['changed'])}"
            )
        print(
            "tables: "
            f"relocations={'same' if report['relocations_identical'] else 'different'} "
            f"symbols={'same' if report['symbol_table_identical'] else 'different'}"
        )
        print(f"proof: {report['proof']}")
        print(f"next gate: {report['next_gate']}")
    return 1 if args.fail_on_collateral and report["collateral_detected"] else 0


def register_collateral_command(
    commands: argparse._SubParsersAction[Any],
) -> None:
    parser = commands.add_parser(
        "object-collateral",
        help="report translation-unit changes hidden by a function-only match",
        description=(
            "Compare section sizes (including zero-fill), section contents, "
            "relocations, and symbols. Optionally prove that one selected "
            "function is exact while the containing object still changed."
        ),
    )
    parser.add_argument("reference")
    parser.add_argument("candidate")
    parser.add_argument("--symbol", "--function", dest="symbol")
    parser.add_argument("--section", default=".text")
    parser.add_argument("--objdump")
    parser.add_argument(
        "--ignore-section",
        action="append",
        default=list(DEFAULT_IGNORES),
        metavar="GLOB",
        help="section glob to exclude; repeatable",
    )
    parser.add_argument("--timeout", type=float, default=10.0)
    parser.add_argument("--json", action="store_true", help="emit JSON")
    parser.add_argument(
        "--fail-on-collateral",
        action="store_true",
        help="return exit 1 when any scoped collateral remains",
    )
    parser.set_defaults(
        handler=collateral_command,
        report_command="object-collateral",
    )
