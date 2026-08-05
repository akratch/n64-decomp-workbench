"""CLI for validating externally generated experiment manifests."""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from .composition import compose_sources, inspect_source, load_composition
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


def experiment_compose_command(args: argparse.Namespace) -> int:
    try:
        report = compose_sources(
            load_composition(args.manifest),
            args.output,
            max_order=args.max_order,
            max_candidates=args.max_candidates,
            write=not args.dry_run,
        )
    except (OSError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        mode = "planned" if args.dry_run else "generated"
        print(
            f"composition: {report['generated_candidates']} candidate(s) {mode}; "
            f"cross-family={report['cross_family_candidates']} "
            f"rejected={len(report['rejected_combinations'])}"
        )
        if report["output"]:
            print(f"experiment: {report['output']}/experiment.json")
        for item in report["rejected_combinations"][:5]:
            names = "+".join(item["transformations"])
            print(f"rejected: {names}: {item['error']}")
        if len(report["rejected_combinations"]) > 5:
            remaining = len(report["rejected_combinations"]) - 5
            print(f"rejected: ... and {remaining} more (use --json for all)")
        for step in report["next_steps"]:
            print(f"next: {step}")
        print(f"proof: {report['proof']}")
    return 1 if report["rejected_combinations"] else 0


def experiment_inspect_source_command(args: argparse.Namespace) -> int:
    try:
        report = inspect_source(args.source)
    except (OSError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(f"source inspection: {report['finding_count']} candidate construct(s)")
        for item in report["findings"]:
            print(f"line {item['line']}: {item['kind']}: {item['source']}")
        for item in report["duplicate_empty_controls"]:
            print(
                "duplicate empty control: "
                f"count={item['count']} lines={','.join(map(str, item['lines']))}"
            )
        print(f"proof: {report['proof']}")
        print(f"next gate: {report['next_gate']}")
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
    inspect = operations.add_parser(
        "inspect-source",
        help="inventory suspicious fake-match constructs before minimization",
    )
    inspect.add_argument("source")
    inspect.add_argument("--json", action="store_true", help="emit JSON")
    inspect.set_defaults(
        handler=experiment_inspect_source_command,
        report_command="experiment-inspect-source",
    )
    compose = operations.add_parser(
        "compose",
        help="generate a bounded cross-mechanism candidate set",
    )
    compose.add_argument("manifest")
    compose.add_argument("output")
    compose.add_argument("--max-order", type=int)
    compose.add_argument("--max-candidates", type=int)
    compose.add_argument(
        "--dry-run", action="store_true", help="validate and plan without writing"
    )
    compose.add_argument("--json", action="store_true", help="emit JSON")
    compose.set_defaults(
        handler=experiment_compose_command,
        report_command="experiment-compose",
    )
