"""CLI for proof-aware target queue classification."""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from .evidence import EvidenceError, load_json_object
from .readiness import readiness_report


def target_readiness_command(args: argparse.Namespace) -> int:
    try:
        report = readiness_report(load_json_object(args.queue, where="target queue"))
    except (EvidenceError, OSError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        counts = report["counts"]
        print(
            "target readiness: " + " ".join(f"{name}={counts[name]}" for name in counts)
        )
        for row in report["targets"]:
            print(f"{row['class']:<20s} {row['symbol']}: {row['next']}")
    return 0


def register_readiness_command(commands: argparse._SubParsersAction[Any]) -> None:
    parser = commands.add_parser(
        "target-readiness",
        help="separate fresh source targets from identity and remeasurement work",
        description=(
            "Re-hash every artifact in a target queue, reject stale measurements, "
            "and split codegen-ready, identity-maintenance, remeasurement, and "
            "promotion-ready work before lanes are assigned."
        ),
    )
    parser.add_argument("queue", help="decomp-workbench-target-queue-v1 JSON")
    parser.add_argument("--json", action="store_true", help="emit JSON")
    parser.set_defaults(
        handler=target_readiness_command, report_command="target-readiness"
    )


__all__ = ["register_readiness_command"]
