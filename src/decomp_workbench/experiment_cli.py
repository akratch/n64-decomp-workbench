"""CLI for validating externally generated experiment manifests."""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from .composition import (
    compose_sources,
    inspect_source,
    load_composition,
    review_mutation,
)
from .experiments import expected_parameter_combinations, load_experiment


def experiment_validate_command(args: argparse.Namespace) -> int:
    try:
        manifest = load_experiment(args.manifest)
        declared = expected_parameter_combinations(manifest)
        excluded = int(manifest.coverage.get("excluded", 0))
        proof = (
            "Schema, paths, assignments, parameter membership, uniqueness, "
            "and selected-region bounds validated"
        )
        if manifest.schema == "decomp-workbench-experiment-v2":
            proof += (
                "; signal/control references, control-source hash identity, "
                "and coverage bounds validated"
            )
        report = {
            **manifest.as_dict(),
            "declared_combinations": declared,
            "described_candidates": len(manifest.candidates),
            "complete_grid": len(manifest.candidates) == declared,
            "accounted_combinations": len(manifest.candidates) + excluded,
            "coverage_complete": len(manifest.candidates) + excluded == declared,
            "signal_count": len(manifest.signals),
            "control_count": len(manifest.controls),
            "identity": manifest.identity_receipt(),
            "proof": proof + "; no candidate was compiled.",
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
        print(f"schema: {report['schema']}")
        print(
            f"candidates: {report['described_candidates']} described / "
            f"{report['declared_combinations']} Cartesian combination(s)"
        )
        print(
            "grid: " + ("COMPLETE" if report["complete_grid"] else "PARTIAL (explicit)")
        )
        if report["schema"] == "decomp-workbench-experiment-v2":
            print(
                f"executable evidence: {report['signal_count']} signal(s), "
                f"{report['control_count']} control(s); coverage accounted "
                f"{report['accounted_combinations']}/"
                f"{report['declared_combinations']}"
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
            step=args.step,
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
        print(report["coverage"]["sentence"])
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
            print(f"  ask: {item['review_question']}")
        for item in report["duplicate_empty_controls"]:
            print(
                "duplicate empty control: "
                f"count={item['count']} lines={','.join(map(str, item['lines']))}"
            )
        print(f"proof: {report['proof']}")
        print(f"next gate: {report['next_gate']}")
        print("cleanup gates:")
        for number, gate in enumerate(report["cleanup_gates"], 1):
            print(f"  {number}. {gate}")
    return 0


def experiment_review_mutation_command(args: argparse.Namespace) -> int:
    try:
        report = review_mutation(args.baseline, args.variant, context=args.context)
    except (OSError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        state = "UNREVIEWED" if report["findings"] else "NO KNOWN INVALID SHAPE"
        print(
            f"mutation review: {state} ({report['errors']} error(s), "
            f"{report['warnings']} warning(s))"
        )
        print(
            f"changed lines: -{report['changed_lines_removed']} "
            f"+{report['changed_lines_added']}"
        )
        for finding in report["findings"]:
            location = f":{finding['line']}" if finding["line"] is not None else ""
            print(
                f"{str(finding['severity']).upper()} {finding['code']}"
                f"{location}: {finding['message']}"
            )
            print(f"  do: {finding['action']}")
        if not args.no_diff:
            for line in report["diff"]:
                print(line)
        print(f"proof: {report['proof']}")
        print(f"next gate: {report['next_gate']}")
    failed = bool(report["errors"]) or (args.fail_on_warning and report["warnings"])
    return 1 if failed else 0


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
    review = operations.add_parser(
        "review-mutation",
        help="diff a sweep winner and name the shapes that invalidate one",
        description=(
            "Print the baseline-to-variant diff a mutation-sweep winner must "
            "be justified against, and flag the two shapes that made a "
            "recorded sweep emit variants that compiled, scored, and were not "
            "the same program: a read that reaches no definition, and a "
            "removed write whose value is still read. Textual review only -- a "
            "clean report is not a validity claim."
        ),
    )
    review.add_argument("baseline", help="source the sweep mutated")
    review.add_argument("variant", help="candidate the sweep produced")
    review.add_argument(
        "--context",
        type=int,
        default=3,
        help="diff context lines (default: 3)",
    )
    review.add_argument(
        "--no-diff",
        action="store_true",
        help="print findings only; the diff is the review surface, so prefer it",
    )
    review.add_argument(
        "--fail-on-warning",
        action="store_true",
        help="return exit 1 for a warning as well as an error",
    )
    review.add_argument("--json", action="store_true", help="emit JSON")
    review.set_defaults(
        handler=experiment_review_mutation_command,
        report_command="experiment-review-mutation",
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
        "--step",
        type=int,
        default=1,
        metavar="N",
        help=(
            "visit every Nth combination, sampling a space too large to "
            "enumerate instead of failing the cap. The record says so: a "
            "sampled sweep reports the stride and the points it never "
            "visited, because a negative result over one point in eight is "
            "not a proof about the other seven (default: 1, exhaustive)"
        ),
    )
    compose.add_argument(
        "--dry-run", action="store_true", help="validate and plan without writing"
    )
    compose.add_argument("--json", action="store_true", help="emit JSON")
    compose.set_defaults(
        handler=experiment_compose_command,
        report_command="experiment-compose",
    )
