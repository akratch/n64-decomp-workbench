"""Command journey for the two source-level probes."""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from .csource import CSourceError
from .source_probe import (
    DEADREAD_LIMITS,
    EQUALITY_LIMITS,
    GUARDED,
    REACH_MODES,
    SPELLINGS,
    dead_read_report,
    value_equality_report,
    write_variants,
)
from .terminal import add_terminal_arguments, emit_lines

__all__ = ["register_source_probe_commands"]


def _limit_lines(limits: tuple[str, ...]) -> list[str]:
    lines = ["", "what this does not know:"]
    for item in limits:
        lines.append(f"  - {item}")
    return lines


def equiv_command(args: argparse.Namespace) -> int:
    try:
        report = value_equality_report(
            args.source, variable=args.variable, positions=tuple(args.at)
        )
    except CSourceError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0

    lines = [
        f"value equality: {report['source']}  variable={report['variable']}",
        f"  declared at line {report['declared_at'] or '-'}; "
        f"{len(report['definitions'])} definition(s); "
        f"{len(report['reads'])} read(s)",
        f"  {report['callee_safe_reason']}",
        "",
        " range  defined  lines            reads  note",
    ]
    for item in report["ranges"]:
        note = "same value at every read"
        if item["control_breaks"]:
            note = "NOT ONE RANGE: a label or goto is inside it"
        elif item["loops"]:
            note = "spans a loop body: a back-edge can carry a definition"
        span = f"{item['first_line']}..{item['last_line']}"
        lines.append(
            f" {item['index']:<6d} {item['defined_at']:<8d} {span:<16s} "
            f"{item['read_count']:<6d} {note}"
        )
    if not report["ranges"]:
        lines.append(" (no definition of this variable, so no range to report)")
    for pair in report.get("pairs", []):
        first, second = pair["lines"]
        lines.append("")
        lines.append(f"lines {first} and {second}: {pair['verdict']}")
        for reason in pair["reasons"]:
            lines.append(f"  {reason}")
    lines.extend(_limit_lines(EQUALITY_LIMITS))
    emit_lines(lines, width=args.width, pager=args.pager)
    return 0


def deadread_command(args: argparse.Namespace) -> int:
    try:
        spellings = (
            SPELLINGS
            if args.spellings == "all"
            else GUARDED
            if args.spellings == "guarded"
            else tuple(item for item in SPELLINGS if item.text == args.spellings)
        )
        if not spellings:
            known = ", ".join(item.text for item in SPELLINGS)
            print(
                f"error: unknown --spellings {args.spellings!r}; use 'guarded', "
                f"'all', or one of: {known}",
                file=sys.stderr,
            )
            return 2
        report = dead_read_report(
            args.source,
            variable=args.variable,
            spellings=spellings,
            limit=args.limit,
            reach=args.reach,
        )
        variants: list[dict[str, str]] = []
        if args.write:
            variants = write_variants(
                report,
                directory=args.write,
                spelling=args.spelling,
                variable=args.variable,
                source=args.source,
            )
    except CSourceError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    except OSError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2

    if args.json:
        report = dict(report)
        report["written_variants"] = variants
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0

    excluded = report["excluded"]
    lines = [
        f"dead-read probe: {report['source']}  variable={report['variable']}",
        f"  declared at line {report['declared_at'] or '-'}; "
        f"definitions at {', '.join(str(item) for item in report['definitions'][:8])}"
        + (" ..." if len(report["definitions"]) > 8 else ""),
        f"  {report['candidate_count']} candidate position(s) of "
        f"{report['statement_positions']}; "
        f"{report['loop_free_count']} outside any loop, "
        f"{report['dominated_count']} reached by a definition on every path",
        "  excluded: "
        + ", ".join(f"{value} {name}" for name, value in excluded.items()),
        "",
        "A discarded read costs zero instructions and still adds an occurrence "
        "to the variable's web, which is what can drive the web memory-"
        "resident. It leaves nothing in the object, so no disassembly diff "
        "will ever point at it.",
        "",
        " spelling            footprint  note",
    ]
    for item in report["spellings"]:
        lines.append(
            f" {item['spelling']:<19s} {item['footprint']:<10s} {item['note']}"
        )
    lines.extend(
        (
            "",
            " line   depth  loop  reached-by    statement",
            " (a bracketed reached-by is a definition in a branch that has "
            "closed: the read is still zero-footprint, but it is not a read "
            "of a value every path assigned)",
        )
    )
    for item in report["candidates"]:
        reached = ",".join(str(number) for number in item["reached_by"][:3])
        if not item["dominated"]:
            reached = f"({reached})"
        lines.append(
            f" {item['line']:<6d} {item['depth']:<6d} "
            f"{'LOOP' if item['in_loop'] else '-':<5s} {reached:<13s} "
            f"{item['before'][:60]}"
        )
    if report["candidates"]:
        first = report["candidates"][0]
        lines.extend(
            (
                "",
                f"patch for line {first['line']}:",
                *(f"  {patch['insert']}" for patch in first["patches"]),
            )
        )
    if variants:
        lines.extend(
            (
                "",
                f"wrote {len(variants)} variant source(s) to {args.write}; "
                "build them with the sweep driver this project already has",
            )
        )
    lines.extend(_limit_lines(DEADREAD_LIMITS))
    emit_lines(lines, width=args.width, pager=args.pager)
    return 0


def register_source_probe_commands(commands: argparse._SubParsersAction[Any]) -> None:
    """Register ``probe-equiv`` and ``probe-deadread``."""

    equiv = commands.add_parser(
        "probe-equiv",
        help="report the ranges over which every read of a local is one value",
        description=(
            "A local whose address never escapes cannot be written by a "
            "callee, so between two of its definitions its value is fixed and "
            "every read in that span is the same value -- which makes two "
            "differently-spelled expressions built from those reads equal. "
            "One campaign's closing lever was exactly this fact, and five "
            "stages searched the register allocator for it because nothing "
            "named the check. This is a probe over the text and the block "
            "structure, not a verifier: every limit it has is printed with "
            "the report."
        ),
        epilog=(
            "example: decomp-workbench probe-equiv work.c --variable sp4B8 "
            "--at 920 --at 991"
        ),
    )
    equiv.add_argument("source", help="C source file")
    equiv.add_argument(
        "--variable", required=True, metavar="NAME", help="the local to reason about"
    )
    equiv.add_argument(
        "--at",
        type=int,
        action="append",
        default=[],
        metavar="LINE",
        help="answer the pairwise question for these lines too; repeatable",
    )
    equiv.add_argument("--json", action="store_true", help="emit JSON")
    add_terminal_arguments(equiv)
    equiv.set_defaults(handler=equiv_command, report_command="probe-equiv")

    deadread = commands.add_parser(
        "probe-deadread",
        help="list positions where a zero-footprint discarded read can be tried",
        description=(
            "A statement that reads a local and drops the value emits no "
            "instructions and still adds an occurrence to the variable's web. "
            "That is enough to change an allocator decision, and it is "
            "invisible to every object-level diff, because nothing was "
            "emitted on either side. This lists the statement positions where "
            "a definition structurally reaches the variable, ranks the ones "
            "outside any loop first, and prints the spelling table with the "
            "footprint each one measured."
        ),
        epilog=(
            "example: decomp-workbench probe-deadread work.c --variable sp4A0 "
            "--limit 20"
        ),
    )
    deadread.add_argument("source", help="C source file")
    deadread.add_argument(
        "--variable", required=True, metavar="NAME", help="the local to read"
    )
    deadread.add_argument(
        "--spellings",
        default="guarded",
        metavar="WHICH",
        help=(
            "which spellings to print patches for: 'guarded' (the "
            "zero-footprint value-guarded forms, the default), 'all', or one "
            "exact spelling"
        ),
    )
    deadread.add_argument(
        "--reach",
        choices=REACH_MODES,
        default="dominating",
        help=(
            "which positions count: 'dominating' keeps only those a "
            "definition structurally reaches, so the read is of a value every "
            "path assigned; 'textual' keeps every position after the first "
            "definition line, which is the wider set the campaign's own sweep "
            "used and where several of its kills were found "
            "(default: dominating)"
        ),
    )
    deadread.add_argument(
        "--limit",
        type=int,
        metavar="N",
        help="show only the first N candidates (they are ranked loop-free first)",
    )
    deadread.add_argument(
        "--write",
        metavar="DIR",
        help=(
            "also write one variant source per candidate into this directory, "
            "ready for the project's own sweep driver"
        ),
    )
    deadread.add_argument(
        "--spelling",
        default="if (V != 0.0f);",
        metavar="TEXT",
        help=(
            "the spelling --write inserts, with V standing for the variable "
            "(default: if (V != 0.0f);)"
        ),
    )
    deadread.add_argument("--json", action="store_true", help="emit JSON")
    add_terminal_arguments(deadread)
    deadread.set_defaults(handler=deadread_command, report_command="probe-deadread")
