"""CLI for the preprocessor-conditional audit (`decomp-workbench context lint`)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from .context_lint import (
    CONTEXT_LINT_SCHEMA,
    duplicate_file_scope_definitions,
    lint_files,
    parse_defines,
    render_report,
)
from .discovery import subcommand_listing_handler


def context_lint_command(args: argparse.Namespace) -> int:
    try:
        defines = parse_defines(args.define)
        report = lint_files(args.files, defines)
    except (OSError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(report.as_dict(), indent=2, sort_keys=True))
    else:
        for line in render_report(report):
            print(line)
    if args.fail_on_high and any(
        finding.severity == "high" for finding in report.findings
    ):
        return 1
    return 0


def context_duplicates_command(args: argparse.Namespace) -> int:
    if len(args.files) < 2:
        print("error: context duplicates requires at least two files", file=sys.stderr)
        return 2
    try:
        sources = [
            (path, Path(path).read_text(encoding="utf-8")) for path in args.files
        ]
        findings = duplicate_file_scope_definitions(sources)
    except OSError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    if args.json:
        print(
            json.dumps(
                {
                    "schema": "decomp-workbench-context-duplicates-v1",
                    "files": args.files,
                    "findings": findings,
                    "limitations": (
                        "single-line file-scope definitions only; this is an "
                        "honest approximation, not a C parser"
                    ),
                },
                indent=2,
                sort_keys=True,
            )
        )
    else:
        print(
            f"context duplicates: {len(findings)} repeated definition(s) "
            f"across {len(args.files)} file(s)"
        )
        for finding in findings:
            locations = ", ".join(
                f"{item['source']}:{item['line']}" for item in finding["occurrences"]
            )
            print(f"  {finding['symbol']}: {locations}")
        if not findings:
            print("no repeated file-scope definition found")
        print("note: scans simple single-line definitions; it is not a C parser")
    return 1 if args.fail_on_findings and findings else 0


def register_context_commands(commands: argparse._SubParsersAction[Any]) -> None:
    parser = commands.add_parser(
        "context",
        help="audit #if/#elif guards for the undefined-identifier-collapse trap",
        description=(
            "Scan C sources for #if/#elif conditionals whose expression's "
            "identifiers are all undefined, so the guard silently evaluates "
            "to a constant no one intended."
        ),
    )
    operations = parser.add_subparsers(dest="context_command")
    parser.set_defaults(handler=subcommand_listing_handler(parser))

    lint = operations.add_parser(
        "lint",
        help="report every collapsed-by-absence #if/#elif guard",
        description=(
            "Parse every #if/#elif in the given files against the macros you "
            "name with --define plus whatever the files #define along the "
            "way, and report guards whose truth was decided entirely by "
            "identifiers that were never defined."
        ),
    )
    lint.add_argument(
        "files",
        nargs="+",
        help="C source or header files to scan, in the order a compiler would see them",
    )
    lint.add_argument(
        "--define",
        action="append",
        default=[],
        metavar="NAME[=VALUE]",
        help=(
            "a macro this translation unit defines, as a compiler -D flag "
            "would; repeatable, and later entries may reference earlier ones"
        ),
    )
    lint.add_argument(
        "--fail-on-high",
        action="store_true",
        help="return exit 1 if any always-true-by-absence finding is present",
    )
    lint.add_argument("--json", action="store_true", help="emit JSON")
    lint.set_defaults(handler=context_lint_command, report_command="context-lint")

    duplicates = operations.add_parser(
        "duplicates",
        help="find simple file-scope definitions repeated across source fragments",
    )
    duplicates.add_argument("files", nargs="+", help="two or more C source fragments")
    duplicates.add_argument(
        "--fail-on-findings",
        action="store_true",
        help="return exit 1 when a repeated definition is found",
    )
    duplicates.add_argument("--json", action="store_true", help="emit JSON")
    duplicates.set_defaults(
        handler=context_duplicates_command,
        report_command="context-duplicates",
    )


__all__ = [
    "CONTEXT_LINT_SCHEMA",
    "context_duplicates_command",
    "context_lint_command",
    "register_context_commands",
]
