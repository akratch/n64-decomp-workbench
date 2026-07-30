"""CLI for linked-address relocation alias evidence."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from .objdump import parse_disassembly
from .relocation_alias import load_symbol_map, relocation_alias_report


def relocation_aliases_command(args: argparse.Namespace) -> int:
    try:
        target = parse_disassembly(
            Path(args.target).read_text(encoding="utf-8"),
            symbol=args.symbol,
        )
        candidate = parse_disassembly(
            Path(args.candidate).read_text(encoding="utf-8"),
            symbol=args.symbol,
        )
        if not target or not candidate:
            raise ValueError("both dumps must contain the selected instruction stream")
        report = relocation_alias_report(
            target,
            candidate,
            symbols=load_symbol_map(args.symbol_map),
        )
    except (OSError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(
            f"relocation aliases: {report['alias_count']} resolved-address "
            f"equivalent pair(s), "
            f"{len(report['unresolved_spelling_differences'])} unresolved"
        )
        for item in report["resolved_address_aliases"]:
            print(
                f"index={item['index']} "
                f"{item['target']['expression']} == "
                f"{item['candidate']['expression']} -> "
                f"0x{item['resolved_address']:x}"
            )
        print(f"proof: {report['proof']}")
    return 0 if report["alias_count"] else 1


def register_relocation_command(
    commands: argparse._SubParsersAction[Any],
) -> None:
    parser = commands.add_parser(
        "relocation-aliases",
        help="resolve relocation spellings through a supplied linked symbol map",
    )
    parser.add_argument("target", help="target GNU objdump text")
    parser.add_argument("candidate", help="candidate GNU objdump text")
    parser.add_argument("--symbol")
    parser.add_argument("--symbol-map", required=True, help="JSON or nm-style map")
    parser.add_argument("--json", action="store_true", help="emit JSON")
    parser.set_defaults(handler=relocation_aliases_command)
