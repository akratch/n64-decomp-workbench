"""CLI for `matrix`: run pipeline variants and cluster them into attractors."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from .matrix import MatrixReport, VariantResult, run_matrix
from .score import ScoreError


def matrix_payload(report: MatrixReport) -> dict[str, Any]:
    return {"schema": "decomp-workbench-matrix-v1", **report.as_dict()}


def render_matrix_human(report: MatrixReport) -> None:
    print(f"run directory (logs never discarded): {report.run_dir}")
    scored = sum(1 for item in report.variants if item.score is not None)
    print(
        f"{len(report.variants)} variant(s), {scored} scored, "
        f"{len(report.attractors)} attractor(s)"
    )
    print(f"{'ATTR':<5}{'DIFF':>6}  MEMBERS")
    for attractor in report.attractors:
        note = ""
        if len(attractor.members) >= 2:
            note = "  <- SAME OUTPUT (silent fallback? see labels)"
        print(
            f"{attractor.letter:<5}{attractor.diff_words:>6}  "
            f"{', '.join(attractor.members)}{note}"
        )
    failed: list[VariantResult] = [
        item for item in report.variants if item.score is None
    ]
    if failed:
        print("")
        print("no scorable object:")
        for item in failed:
            print(f"  {item.label}: {item.error}")
    if report.silent_fallback_warnings:
        print("")
        print("stderr warnings (possible silent flag fallback):")
        for label, line in report.silent_fallback_warnings:
            print(f"  {label}: {line}")
    if report.collapsed_attractors and not report.all_collapsed:
        print("")
        for attractor in report.collapsed_attractors:
            members = ", ".join(attractor.members)
            print(
                f"NOTE: attractor {attractor.letter} contains "
                f"{len(attractor.members)} differently-labeled variants that "
                f"produced identical bytes: {members}"
            )
    if report.caution:
        print("")
        print(f"CAUTION: {report.caution}")
    print("")
    if report.attractors:
        best_labels = set(report.attractors[0].members)
        best = next(
            (
                item
                for item in report.variants
                if item.label in best_labels and item.score is not None
            ),
            None,
        )
        if best is not None:
            assert best.score is not None
            for step in best.score.guidance:
                print(f"next: {step}")


def matrix_command(args: argparse.Namespace) -> int:
    try:
        report = run_matrix(
            args.spec,
            run_dir=Path(args.run_dir) if args.run_dir else None,
            timeout=args.timeout,
        )
    except (ScoreError, OSError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(matrix_payload(report), indent=2, sort_keys=True))
    else:
        render_matrix_human(report)
    return 0 if any(item.score is not None for item in report.variants) else 1


def register_matrix_command(commands: Any) -> None:
    parser = commands.add_parser(
        "matrix",
        help="run pipeline variants and cluster their output into attractors",
        description=(
            "Run every variant command in a JSON spec, substituting $OUTPUT "
            "for a per-variant object path, then score and hash each "
            "produced object. Identical hashes cluster into lettered "
            "attractors (A is the closest to matching); two or more "
            "differently-labeled variants sharing one attractor, or every "
            "variant collapsing into one, are called out explicitly, because "
            "a silently-ignored flag looks identical to an exhausted search "
            "axis otherwise."
        ),
    )
    parser.add_argument(
        "spec", help="matrix JSON spec file (see docs/score-and-matrix.md)"
    )
    parser.add_argument(
        "--run-dir",
        help=(
            "directory for produced objects and per-variant stdout/stderr "
            "logs (default: .decomp-workbench/matrix/<timestamp>)"
        ),
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=120.0,
        help="per-variant command timeout in seconds (default: 120)",
    )
    parser.add_argument("--json", action="store_true", help="emit JSON")
    parser.set_defaults(handler=matrix_command)
