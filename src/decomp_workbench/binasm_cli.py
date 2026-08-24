"""CLI for retained IDO Binasm and as1 peephole-boundary evidence."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from .binasm import build_binasm_boundary_report


def _integer(value: str) -> int:
    try:
        return int(value, 0)
    except ValueError as error:
        raise argparse.ArgumentTypeError(
            f"expected a decimal or 0x-prefixed integer, got {value!r}"
        ) from error


def binasm_boundary_command(args: argparse.Namespace) -> int:
    try:
        peep_text = (
            Path(args.peep_log).read_text(encoding="utf-8") if args.peep_log else None
        )
        probe_results = (
            json.loads(Path(args.probe_results).read_text(encoding="utf-8"))
            if args.probe_results
            else None
        )
        report = build_binasm_boundary_report(
            args.stream,
            boundary=args.boundary,
            radius=args.radius,
            byteorder=args.byteorder,
            peep_text=peep_text,
            probe_results=probe_results,
            limit=args.limit,
        )
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0

    stream = report["stream"]
    boundary = report["boundary"]
    print(
        f"Binasm: {stream['record_count']} record(s), {stream['bytes']} bytes, "
        f"sha256={stream['sha256'][:12]}"
    )
    print(
        f"boundary: {boundary['offset_hex']} before record {boundary['record_index']}"
    )
    for item in boundary["window"]:
        marker = ">" if item["boundary_before"] else " "
        lever = f"; lever={item['source_lever']}" if item["source_lever"] else ""
        print(
            f"{marker} {item['offset_hex']:>8s} #{item['index']:04d} "
            f"{item['raw_hex']}  {item['name']}: {item['detail']}{lever}"
        )

    peephole = report.get("peephole")
    if peephole is not None:
        print(
            "peephole: "
            f"events={peephole['event_count']} "
            f"replacement+NOP pairs={peephole['replacement_nop_pair_count']} "
            f"unparsed={peephole['unparsed_debug_line_count']}"
        )
        for pair in peephole["replacement_nop_pairs"]:
            replacement = pair["replacement"]
            removed = pair["removed_copy"]
            print(
                f"  {replacement['family']} INST {replacement['inst']} "
                f"registers {replacement['register']}/{replacement['with_register']}; "
                f"INST {removed['inst']} -> NOP"
            )
        print(f"  scope: {peephole['correlation_scope']}")

    probes = report.get("barrier_probes")
    if probes is not None:
        print(
            f"barrier probes: {probes['exact_count']}/{probes['probe_count']} exact; "
            f"families={probes['family_counts'] or 'none'}; "
            f"sites={probes['site_counts'] or 'none'}"
        )
        for lever in probes["source_search"]:
            print(
                f"  next ({lever['family']}, {lever['exact_count']} exact): "
                f"{lever['next']}"
            )
        print(f"  claim: {probes['strongest_claim']}")
    print(f"proof: {report['proof']}")
    return 0


def register_binasm_command(
    commands: argparse._SubParsersAction[Any],
) -> None:
    parser = commands.add_parser(
        "inspect-binasm",
        help="inspect one retained IDO Binasm peephole boundary",
        description=(
            "Read IDO's fixed 16-byte ugen-to-as1 stream around one insertion "
            "boundary, optionally summarize -peepdbg output and exact barrier "
            "probe results. This command is static and does not run a compiler."
        ),
    )
    parser.add_argument("stream", help="retained Binasm stream (commonly .G)")
    parser.add_argument(
        "--boundary",
        required=True,
        type=_integer,
        help="aligned byte insertion offset, decimal or 0x-prefixed",
    )
    parser.add_argument(
        "--radius",
        type=int,
        default=4,
        help="records shown before and after the boundary (default: 4)",
    )
    parser.add_argument(
        "--byteorder",
        choices=("big", "little"),
        default="big",
        help="word byte order (default: big, as used by N64 IDO streams)",
    )
    parser.add_argument(
        "--peep-log",
        help="optional IDO 7.1 -peepdbg stdout/stderr capture",
    )
    parser.add_argument(
        "--probe-results",
        help="optional barrier sweep JSON containing results[].exact/name",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=50,
        help="maximum peephole/probe evidence rows retained (default: 50)",
    )
    parser.add_argument("--json", action="store_true", help="emit JSON")
    parser.set_defaults(handler=binasm_boundary_command)
