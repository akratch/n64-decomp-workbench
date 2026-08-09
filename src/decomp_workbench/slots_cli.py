"""Command journey for the stack-slot traffic census."""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from .cascade import parse_row_range
from .cli_options import add_explain_keys_argument, add_symbol_argument
from .csource import CSourceError
from .dis_cache import DisassemblyCache
from .row_source import load_dump_rows, load_object_rows
from .slots import slot_report, volatile_probe_sources
from .terminal import add_terminal_arguments, emit_lines

__all__ = ["register_slots_command"]


def slots_command(args: argparse.Namespace) -> int:
    try:
        rows = parse_row_range(args.rows) if args.rows else None
        if args.dumps:
            instructions = load_dump_rows(args.object, symbol=args.symbol)
        else:
            cache = (
                DisassemblyCache(args.disassembly_cache)
                if args.disassembly_cache
                else None
            )
            instructions = load_object_rows(
                args.object,
                objdump=args.objdump,
                symbol=args.symbol,
                section=args.section,
                cache=cache,
            )
        report = slot_report(
            instructions, label=args.object, rows=rows, minimum=args.min_rows
        )
        probe = None
        if args.volatile_probe:
            if not args.source:
                raise CSourceError(
                    "--volatile-probe needs --source SOURCE: it writes one "
                    "variant of that file per local, each with that local made "
                    "volatile so the compiler must keep it in memory"
                )
            probe = volatile_probe_sources(
                args.source,
                directory=args.volatile_probe,
                variables=tuple(args.variable),
            )
    except (CSourceError, OSError, RuntimeError, ValueError) as error:
        # RuntimeError is what a failed objdump raises, and it names the file
        # and quotes the tool: a census refused for an unreadable object is a
        # refusal, not a crash.
        print(f"error: {error}", file=sys.stderr)
        return 2

    if args.json:
        payload = dict(report)
        if probe is not None:
            payload["volatile_probe"] = probe
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0

    frame = report["frame"]
    lines = [
        f"stack slots: {report['object']}  {report['slot_count']} slot(s) "
        f"over rows {report['rows'][0]}..{report['rows'][1]}  "
        f"{report['touched_rows']} touching row(s)"
        + (f"  frame={frame}" if frame is not None else ""),
        "",
        " slot     frameoff    rows  ld   st   addr  widths   registers"
        if frame is not None
        else " slot     rows  ld   st   addr  widths   registers",
    ]
    for item in report["slots"]:
        widths = ",".join(str(width) for width in item["widths"]) or "-"
        registers = ",".join(item["registers"][: args.registers]) or "-"
        if len(item["registers"]) > args.registers:
            registers += ",..."
        flag = "  PUN" if item["punned"] else ""
        # The trace spells a site as an unsigned 32-bit frame offset
        # (0xfffffdf8); print it that way beside the signed value so a reader
        # can paste it straight into `trace-cascade --frame-offset`.
        offset = item["frame_offset"]
        joint = (
            f"{offset & 0xFFFFFFFF:#010x} "
            if offset is not None and offset < 0
            else f"{offset:<10d} "
            if offset is not None
            else ""
        )
        lines.append(
            f" {item['offset']:<8d} {joint}{item['total']:<5d} "
            f"{item['loads']:<4d} "
            f"{item['stores']:<4d} {item['address_taken']:<5d} "
            f"{widths:<8s} {registers}{flag}"
        )
    if any(item["punned"] for item in report["slots"]):
        lines.append("")
        lines.append(
            "PUN: more than one access width reaches this offset. That is one "
            "storage location under two spellings, not two variables -- and "
            "the allocator keys webs on storage, not on the C name."
        )
    if report["slots"]:
        cheapest = ", ".join(
            f"{item['offset']}({item['total']} row(s))" for item in report["cheapest"]
        )
        lines.extend(
            (
                "",
                f"cheapest slots to disturb: {cheapest}",
                "A donor's price is the number of rows that touch its slot; "
                "this is that price, without a build.",
            )
        )
    if frame is not None:
        lines.extend(
            (
                "",
                f"slot is sp-relative, as the rows spell it; frameoff is the "
                f"same storage as the allocator trace keys it -- slot + frame "
                f"({frame}). `decomp-workbench trace-cascade LOG "
                "--frame-offset FRAMEOFF` reads that site's decision.",
            )
        )
    lines.extend(("", f"reading: {report['reading']}"))
    if probe is not None:
        lines.extend(
            (
                "",
                f"volatile probe: wrote {probe['count']} variant source(s) to "
                f"{probe['directory']}",
                f"  next: {probe['next']}",
            )
        )
    emit_lines(lines, width=args.width, pager=args.pager)
    return 0


_DESCRIPTION = (
    "Count what an object's rows do to each sp-relative stack slot: loads, "
    "stores, "
    "address-takes, the access widths that reach it and the registers that "
    "carry it. Two campaign questions reduce to this one census -- what a "
    "fusion donor costs (the rows that touch its slot, which one campaign "
    "spent a whole sweep answering by construction) and whether a slot is one "
    "variable or a pun. It reports what the rows do; it does not claim which "
    "C local lives at a slot, because nothing in an object says so. Each slot "
    "is printed both ways -- sp-relative as the rows spell it, and as the "
    "frame offset `trace-cascade` keys a site by -- because 1184 and "
    "0xfffffdf8 are the same storage and only one of them is a command "
    "argument."
)


def register_slots_command(commands: argparse._SubParsersAction[Any]) -> None:
    """Register ``slots``."""

    parser = commands.add_parser(
        "slots",
        help="count the loads, stores and address-takes at each stack slot",
        description=_DESCRIPTION,
        epilog="example: decomp-workbench slots target.o --rows 1900..2200",
    )
    parser.add_argument("object", help="object to read (or dump text with --dumps)")
    parser.add_argument(
        "--rows",
        metavar="LO..HI",
        help="restrict the census to these rows (inclusive)",
    )
    parser.add_argument(
        "--min-rows",
        type=int,
        default=1,
        metavar="N",
        help="hide slots touched fewer than N times (default: 1)",
    )
    parser.add_argument(
        "--registers",
        type=int,
        default=4,
        metavar="N",
        help="registers to name per slot before eliding (default: 4)",
    )
    parser.add_argument(
        "--source",
        metavar="SOURCE",
        help="the C source, for --volatile-probe",
    )
    parser.add_argument(
        "--volatile-probe",
        metavar="DIR",
        help=(
            "also write one variant of --source per local, that local made "
            "`volatile` so the compiler must keep it in memory: build each "
            "and re-run `slots` to learn which slot the compiler gave it"
        ),
    )
    parser.add_argument(
        "--variable",
        action="append",
        default=[],
        metavar="NAME",
        help="restrict --volatile-probe to these locals; repeatable",
    )
    parser.add_argument(
        "--dumps",
        action="store_true",
        help="read retained `objdump -d -r` text rather than an object",
    )
    parser.add_argument(
        "--section", default=".text", help="object section (default: .text)"
    )
    parser.add_argument(
        "--objdump", help="GNU-compatible MIPS objdump; auto-detected when omitted"
    )
    parser.add_argument(
        "--disassembly-cache",
        metavar="DIR",
        help="reuse disassemblies from this directory across runs",
    )
    add_symbol_argument(parser, help_text="read only this exact symbol")
    parser.add_argument("--json", action="store_true", help="emit JSON")
    add_explain_keys_argument(parser)
    add_terminal_arguments(parser)
    parser.set_defaults(handler=slots_command, report_command="slots")
