"""Command-line reporting for IDO 7.1 A71 allocator traces."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from .a71 import A71Record, compare_a71_traces, parse_a71_trace


def _color(record: A71Record) -> str:
    suffix = f" ({record.register})" if record.register else ""
    return f"c{record.color}{suffix}"


def _record_line(marker: str, record: A71Record) -> str:
    forbidden = ",".join(f"c{color}" for color in record.forbidden_colors) or "none"
    return (
        f"{marker} p{record.phase} w{record.web} sym={record.symbol} "
        f"class={record.register_class} priority={record.priority:g} "
        f"[{record.priority_bits:08x}] color={_color(record)} "
        f"forbidden={forbidden}"
    )


def trace_a71_command(args: argparse.Namespace) -> int:
    try:
        baseline = parse_a71_trace(Path(args.trace).read_text(encoding="utf-8"))
        candidate = (
            parse_a71_trace(Path(args.against).read_text(encoding="utf-8"))
            if args.against
            else None
        )
    except (OSError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2

    selected = baseline.selected(
        phase=args.phase, web=args.web, register_class=args.register_class
    )
    if candidate is None:
        report: dict[str, object] = {
            "format": "ido-7.1-a71-final-color",
            "filters": {
                "phase": args.phase,
                "web": args.web,
                "register_class": args.register_class,
            },
            "summary": baseline.summary(selected),
            "records": [record.as_dict() for record in selected],
            "field_warning": (
                "Historical refs/defs fields read invalid recovered-source "
                "offsets and are ignored."
            ),
        }
        if args.json:
            print(json.dumps(report, indent=2, sort_keys=True))
        else:
            summary = report["summary"]
            assert isinstance(summary, dict)
            print(
                f"A71: {summary['record_count']} final-color record(s); "
                f"phases={summary['phase_counts']} classes={summary['class_counts']}"
            )
            for record in selected[: args.limit]:
                print(_record_line(" ", record))
            if len(selected) > args.limit:
                print(f"... {len(selected) - args.limit} more record(s); use --limit")
            print(f"warning: {report['field_warning']}")
        return 0 if selected else 1

    report = compare_a71_traces(
        baseline,
        candidate,
        phase=args.phase,
        web=args.web,
        register_class=args.register_class,
    )
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0

    before_summary = report["baseline_summary"]
    after_summary = report["candidate_summary"]
    assert isinstance(before_summary, dict)
    assert isinstance(after_summary, dict)
    print(
        "A71 diff: "
        f"baseline={before_summary['record_count']} "
        f"candidate={after_summary['record_count']} "
        f"changed_phase_webs={report['difference_count']}"
    )
    changes = report["changes"]
    assert isinstance(changes, list)
    for change in changes[: args.limit]:
        assert isinstance(change, dict)
        left = change["baseline"]
        right = change["candidate"]
        if left is None:
            assert isinstance(right, dict)
            key = (change["phase"], change["web"])
            record = next(item for item in candidate.records if item.key == key)
            print(_record_line("+", record))
        elif right is None:
            key = (change["phase"], change["web"])
            record = next(item for item in baseline.records if item.key == key)
            print(_record_line("-", record))
        else:
            assert isinstance(left, dict)
            assert isinstance(right, dict)
            deltas = []
            for field in change["changed_fields"]:
                display = "priority" if field == "priority_bits" else field
                deltas.append(f"{display}:{left[display]}->{right[display]}")
            print(f"~ p{change['phase']} w{change['web']} " + " ".join(deltas))
    if len(changes) > args.limit:
        print(f"... {len(changes) - args.limit} more change(s); use --limit")
    print(f"warning: {report['alignment_warning']}")
    print(f"warning: {report['field_warning']}")
    return 0


def register_a71_command(commands: argparse._SubParsersAction[Any]) -> None:
    parser = commands.add_parser(
        "trace-a71",
        help="inspect or diff an IDO 7.1 A71 allocator trace",
        description=(
            "Statically parse the compact [A71] final-color stream, decoding "
            "priority bits and masks. With --against, compare run-local "
            "phase/web keys without claiming semantic identity."
        ),
    )
    parser.add_argument("trace", help="filtered .a71 trace or mixed compiler log")
    parser.add_argument("--against", help="candidate A71 trace to compare")
    parser.add_argument("--phase", type=int, choices=(1, 2), help="only this phase")
    parser.add_argument("--web", type=int, help="only this run-local web number")
    parser.add_argument(
        "--class",
        type=int,
        choices=(1, 2),
        dest="register_class",
        help="only this register class",
    )
    parser.add_argument(
        "--limit", type=int, default=50, help="maximum rows shown (default: 50)"
    )
    parser.add_argument("--json", action="store_true", help="emit JSON")
    parser.set_defaults(handler=trace_a71_command)
