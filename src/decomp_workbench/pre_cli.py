"""CLI for PRE/speculative-hoist compiler-decision provenance."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from .pre import (
    compare_pre_traces,
    instrument_pre_source,
    load_pre_profile,
    parse_pre_trace,
    pre_report,
)
from .trace import read_trace_text


def trace_pre_command(args: argparse.Namespace) -> int:
    try:
        if args.proc is not None and args.proc < 0:
            raise ValueError("--proc must be non-negative")
        if args.limit < 0:
            raise ValueError("--limit must be non-negative")
        events, ignored = parse_pre_trace(read_trace_text(args.trace))
        selected = [
            event for event in events if args.proc is None or event.proc == args.proc
        ]
        if args.against:
            candidate, _ = parse_pre_trace(read_trace_text(args.against))
            selected_candidate = [
                event
                for event in candidate
                if args.proc is None or event.proc == args.proc
            ]
            report = compare_pre_traces(selected, selected_candidate)
        else:
            report = pre_report(events, proc=args.proc)
            report["ignored_diagnostic_lines"] = len(ignored)
    except (OSError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    elif args.against:
        print(f"PRE diff: {report['difference_count']} decision(s) differ")
        for item in report["differences"][: args.limit]:
            print(
                f"proc={item['proc']} block={item['block']} "
                f"expression={item['expression']} changed={','.join(item['changed'])}"
            )
    else:
        print(f"PRE: {report['event_count']} decision(s)")
        for item in report["events"][: args.limit]:
            print(
                f"proc={item['proc']} block={item['block']} line={item['line']} "
                f"expression={item['expression']} decision={item['decision']} "
                f"reason={item['reason']}"
            )
        print(f"proof: {report['proof']}")
    return 0 if selected else 1


def instrument_pre_command(args: argparse.Namespace) -> int:
    try:
        source_path = Path(args.input).expanduser().resolve()
        output_path = Path(args.output).expanduser().resolve()
        if source_path == output_path:
            raise ValueError("PRE input and output must be different paths")
        if output_path.exists():
            raise FileExistsError(f"refusing to overwrite output: {output_path}")
        instrumented, report = instrument_pre_source(
            source_path.read_text(encoding="utf-8"), load_pre_profile(args.profile)
        )
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with output_path.open("x", encoding="utf-8") as destination:
            destination.write(instrumented)
        report["output"] = str(output_path)
    except (OSError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(f"PRE profile: {report['injections']} injection(s) -> {output_path}")
        print("required gates: " + ", ".join(report["calibration_required"]))
    return 0


def register_pre_commands(commands: argparse._SubParsersAction[Any]) -> None:
    trace = commands.add_parser(
        "trace-pre",
        help="read PRE and speculative-hoist decision provenance",
        description=(
            "Read stable, procedure-scoped PRE decisions: expression, block, "
            "accept/reject outcome, reason, source line, and optional "
            "availability/cost."
        ),
    )
    trace.add_argument("trace")
    trace.add_argument("--against", help="second trace for identity-aligned diff")
    trace.add_argument("--proc", type=int)
    trace.add_argument("--limit", type=int, default=50)
    trace.add_argument("--json", action="store_true", help="emit JSON")
    trace.set_defaults(handler=trace_pre_command, report_command="trace-pre")

    instrument = commands.add_parser(
        "instrument-pre",
        help="apply a hash-pinned PRE instrumentation profile",
        description=(
            "Apply uniqueness-checked anchors from a project-reviewed profile. "
            "The output becomes evidence only after the listed disabled-trace "
            "fidelity and positive-control gates pass."
        ),
    )
    instrument.add_argument("input")
    instrument.add_argument("output")
    instrument.add_argument("--profile", required=True)
    instrument.add_argument("--json", action="store_true", help="emit JSON")
    instrument.set_defaults(
        handler=instrument_pre_command, report_command="instrument-pre"
    )


__all__ = ["register_pre_commands"]
