"""CLI for semantic allocator and stack-home reports."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from .allocator_analysis import (
    compare_semantic_webs,
    stack_home_report,
    web_report,
)
from .globalcolor import parse_globalcolor_trace


def allocator_webs_command(args: argparse.Namespace) -> int:
    try:
        target = parse_globalcolor_trace(Path(args.trace).read_text(encoding="utf-8"))
        report = (
            compare_semantic_webs(
                target,
                parse_globalcolor_trace(Path(args.against).read_text(encoding="utf-8")),
                proc=args.proc,
            )
            if args.against
            else web_report(target, proc=args.proc)
        )
    except (OSError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    elif args.against:
        print(
            f"allocator semantic diff: {report['difference_count']} difference(s), "
            f"{len(report['ambiguous_fingerprints'])} ambiguous fingerprint(s)"
        )
        for item in report["differences"][: args.limit]:
            print(f"{item['fingerprint']} changed={','.join(item['changed'])}")
        print(f"proof: {report['proof']}")
    else:
        print(
            f"allocator webs: {report['web_count']} semantic fingerprint(s), "
            f"{report['low_confidence']} low-confidence"
        )
        print(
            "source attribution: "
            f"{report['source_attributed_webs']} source-attributed, "
            f"{report['run_local_unattributed_webs']} run-local/unattributed"
        )
        if report["next_gate"]:
            print(f"next gate: {report['next_gate']}")
        for item in report["webs"][: args.limit]:
            print(
                f"{item['fingerprint']} confidence={item['confidence']} "
                f"phase={item['phase']} local=w{item['numeric_web']} "
                f"color={item['assigned_color']} register={item['assigned_register']}"
            )
        print(f"proof: {report['proof']}")
    count = report.get("web_count", report.get("difference_count", 0))
    return 0 if count else 1


def stack_homes_command(args: argparse.Namespace) -> int:
    try:
        trace = parse_globalcolor_trace(Path(args.trace).read_text(encoding="utf-8"))
        report = stack_home_report(trace, proc=args.proc, offset=args.offset)
    except (OSError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(
            f"stack homes: {report['selected_count']} shown / "
            f"{report['home_count']} classified"
        )
        for home in report["homes"][: args.limit]:
            print(
                f"{home['fingerprint']} kind={home['kind']} "
                f"virtual={home['virtual_offset']} final={home['final_offset']} "
                f"source={home['source']}"
            )
        print(f"proof: {report['proof']}")
    return 0 if report["selected_count"] else 1


def register_allocator_commands(
    commands: argparse._SubParsersAction[Any],
) -> None:
    webs = commands.add_parser(
        "trace-webs",
        help="fingerprint allocator webs by semantic provenance",
        description=(
            "Align allocator decisions by dtype, virtual home, formation chain, "
            "and block context; numeric web IDs remain trace-local."
        ),
    )
    webs.add_argument("trace")
    webs.add_argument("--against", help="second trace for semantic web diff")
    webs.add_argument("--proc", type=int)
    webs.add_argument("--limit", type=int, default=50)
    webs.add_argument("--json", action="store_true", help="emit JSON")
    webs.set_defaults(handler=allocator_webs_command)

    homes = commands.add_parser(
        "trace-stack-homes",
        help="classify and query trace-derived stack-home ownership",
    )
    homes.add_argument("trace")
    homes.add_argument("--proc", type=int)
    homes.add_argument(
        "--offset",
        type=lambda value: int(value, 0),
        help="show owners of one virtual or explicitly recorded final offset",
    )
    homes.add_argument("--limit", type=int, default=50)
    homes.add_argument("--json", action="store_true", help="emit JSON")
    homes.set_defaults(handler=stack_homes_command)
