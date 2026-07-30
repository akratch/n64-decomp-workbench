"""CLI for honest allocator trace-to-source/listing correlation."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from .globalcolor import parse_globalcolor_trace
from .source_correlation import correlate_trace_source


def trace_source_command(args: argparse.Namespace) -> int:
    try:
        trace_path = Path(args.trace).expanduser().resolve()
        source_path = Path(args.source).expanduser().resolve()
        listing_path = (
            Path(args.listing).expanduser().resolve() if args.listing else None
        )
        report = correlate_trace_source(
            parse_globalcolor_trace(trace_path.read_text(encoding="utf-8")),
            source_text=source_path.read_text(encoding="utf-8"),
            source_origin=str(source_path),
            listing_text=(
                listing_path.read_text(encoding="utf-8") if listing_path else None
            ),
            source_file=args.source_file,
            proc=args.proc,
        )
    except (OSError, SyntaxError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        states = report["states"]
        print(
            f"trace source: {report['correlated_webs']}/{report['web_count']} "
            "web(s) correlated; "
            f"{states['ambiguous']} ambiguous, {states['unresolved']} unresolved"
        )
        for row in report["webs"][: args.limit]:
            print(
                f"{row['fingerprint']} {row['force_key']} "
                f"line={row['trace_line']} state={row['state']}"
            )
            for source in row["source_candidates"]:
                print(
                    f"  source {source['file']}:{source['line']} "
                    f"{source['text'].strip()}"
                )
            for location in row["listing_locations"]:
                label = location["file"] or f"file#{location['file_index']}"
                print(
                    f"  listing line {location['listing_line']}: "
                    f"{label}:{location['line']}"
                )
        if len(report["webs"]) > args.limit:
            print(f"... {len(report['webs']) - args.limit} more web(s); use --json")
        print(f"proof: {report['proof']}")
    return 0 if report["correlated_webs"] else 1


def register_source_correlation_command(
    commands: argparse._SubParsersAction[Any],
) -> None:
    parser = commands.add_parser(
        "trace-source",
        help="join allocator web lines to preprocessor and listing evidence",
        description=(
            "Map trace logical line numbers through retained #line markers and "
            "optional .file/.loc directives, preserving ambiguous matches."
        ),
    )
    parser.add_argument("trace", help="captured allocator trace")
    parser.add_argument("source", help="retained preprocessed or composed source")
    parser.add_argument("--listing", help="optional retained assembly listing")
    parser.add_argument(
        "--source-file",
        help="select one exact marker filename (or unique basename)",
    )
    parser.add_argument("--proc", type=int, help="include one allocator invocation")
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--json", action="store_true", help="emit JSON")
    parser.set_defaults(handler=trace_source_command)
