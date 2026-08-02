"""Command-line interface for public handoff audits."""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from .handoff_audit import audit_handoff


def audit_handoff_command(args: argparse.Namespace) -> int:
    try:
        report = audit_handoff(
            args.path,
            dependency_roots=args.dependency_root,
            exclude=args.exclude,
        )
    except (OSError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        state = "READY" if report["ready"] else "NEEDS ATTENTION"
        print(
            f"handoff: {state} ({report['errors']} error(s), "
            f"{report['warnings']} warning(s))"
        )
        print(f"root: {report['root']}")
        for finding in report["findings"]:
            location = str(finding["source"])
            if finding["line"] is not None:
                location += f":{finding['line']}"
            reference = f" ({finding['reference']})" if finding["reference"] else ""
            print(
                f"{str(finding['severity']).upper()} {finding['code']} "
                f"{location}{reference}: {finding['message']}"
            )
            print(f"  do: {finding['action']}")
        print(f"proof: {report['proof']}")
    failed = not report["ready"] or (args.fail_on_warning and report["warnings"])
    return 1 if failed else 0


def register_handoff_command(
    commands: argparse._SubParsersAction[Any],
) -> None:
    audit = commands.add_parser(
        "audit-handoff",
        help="catch publication paths and files that will not travel",
        description=(
            "Audit a proof/handoff repository for missing local references, "
            "absolute user paths, and files or dependencies absent from Git."
        ),
    )
    audit.add_argument("path", help="public handoff repository or directory")
    audit.add_argument(
        "--dependency-root",
        action="append",
        default=[],
        metavar="PATH",
        help="project root allowed to satisfy references; repeatable",
    )
    audit.add_argument(
        "--fail-on-warning",
        action="store_true",
        help="return exit 1 for warnings as well as errors",
    )
    audit.add_argument(
        "--exclude",
        action="append",
        default=[],
        metavar="GLOB",
        help="repository-relative path glob to exclude; repeatable",
    )
    audit.add_argument("--json", action="store_true", help="emit JSON")
    audit.set_defaults(handler=audit_handoff_command)
