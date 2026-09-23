"""Command journey for stopping evidence: `campaign stall`."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from .stall import load_series, read_series, stall_payload

__all__ = ["register_stall_command"]


def stall_command(args: argparse.Namespace) -> int:
    try:
        payload = json.loads(Path(args.series).expanduser().read_text(encoding="utf-8"))
        attempts, closed, threshold = load_series(payload)
        if args.threshold is not None:
            threshold = args.threshold
        reading = read_series(
            attempts,
            threshold=threshold,
            closed_by_evidence=closed or args.closed_by_evidence,
        )
    except (OSError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    report = stall_payload(reading, attempts)
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        best = report["best_residual"]
        print(
            f"stall reading: {report['state']} over {report['attempts']} "
            f"attempt(s); best stock residual "
            f"{best if best is not None else '-'}"
        )
        print("\n".join(reading.lines))
    return 0 if reading.should_continue else 1


def register_stall_command(commands: argparse._SubParsersAction[Any]) -> None:
    """Register `campaign-stall` behind the `campaign stall` spelling."""

    parser = commands.add_parser(
        "campaign-stall",
        help=argparse.SUPPRESS,
        description=(
            "Read a series of already-measured attempts and say whether the "
            "next one should happen: `improving` while attempts still move the "
            "best stock residual or eliminate a hypothesis, `stalled` after "
            "THRESHOLD consecutive attempts that did neither, and "
            "`closed-by-evidence` when the target's recorded history already "
            "rules out what is left. Every attempt states how its object was "
            "built; a forced or unknown build never counts as residual "
            "progress. Exit 0 to continue, 1 to stop."
        ),
        epilog=(
            "example: decomp-workbench campaign stall "
            "examples/fixtures/attempt-series.json"
        ),
    )
    parser.add_argument(
        "series", help="a decomp-workbench-attempt-series-v1 JSON document"
    )
    parser.add_argument(
        "--threshold",
        type=int,
        help="consecutive attempts that buy nothing before a stall (default: "
        "the document's, else 3)",
    )
    parser.add_argument(
        "--closed-by-evidence",
        action="store_true",
        help="the target's recorded history already rules out the remaining mechanisms",
    )
    parser.add_argument("--json", action="store_true", help="emit JSON")
    parser.set_defaults(handler=stall_command, report_command="campaign-stall")
