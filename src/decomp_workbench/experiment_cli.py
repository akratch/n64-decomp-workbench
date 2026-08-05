"""CLI for validating externally generated experiment manifests."""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from .experiments import expected_parameter_combinations, load_experiment


def experiment_validate_command(args: argparse.Namespace) -> int:
    try:
        manifest = load_experiment(args.manifest)
        report = {
            **manifest.as_dict(),
            "declared_combinations": expected_parameter_combinations(manifest),
            "described_candidates": len(manifest.candidates),
            "complete_grid": (
                len(manifest.candidates) == expected_parameter_combinations(manifest)
            ),
            "proof": (
                "Schema, paths, assignments, parameter membership, uniqueness, "
                "and selected-region bounds validated; no candidate was compiled."
            ),
        }
    except (OSError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    if args.json or args.json_summary:
        payload = report
        if args.json_summary:
            payload = {
                key: value for key, value in report.items() if key != "candidates"
            }
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(f"experiment: {report['family']} ({report['path']})")
        print(
            f"candidates: {report['described_candidates']} described / "
            f"{report['declared_combinations']} Cartesian combination(s)"
        )
        print(
            "grid: " + ("COMPLETE" if report["complete_grid"] else "PARTIAL (explicit)")
        )
        print(f"proof: {report['proof']}")
    return 0


def register_experiment_commands(
    commands: argparse._SubParsersAction[Any],
) -> None:
    parser = commands.add_parser(
        "experiment",
        help="validate experiment-family manifests before compiling",
    )
    operations = parser.add_subparsers(dest="experiment_command", required=True)
    validate = operations.add_parser(
        "validate",
        help="validate paths, assignments, grid size, and selected region",
    )
    validate.add_argument("manifest")
    output = validate.add_mutually_exclusive_group()
    output.add_argument("--json", action="store_true", help="emit JSON")
    output.add_argument(
        "--json-summary",
        action="store_true",
        help="emit compact JSON without the full candidate list",
    )
    validate.set_defaults(
        handler=experiment_validate_command,
        report_command="experiment-validate",
    )
