"""CLI for generating and reading a compiler phase-capture toolchain."""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from .capture import DEFAULT_PHASES, list_capture_runs, make_capture_toolchain


def _human_bytes(value: int) -> str:
    if value < 1024:
        return f"{value}B"
    if value < 1024 * 1024:
        return f"{value / 1024:.1f}K"
    return f"{value / (1024 * 1024):.1f}M"


def capture_make_command(args: argparse.Namespace) -> int:
    try:
        manifest = make_capture_toolchain(
            args.ido_root,
            args.destination,
            phases=args.phase or DEFAULT_PHASES,
            link=args.link,
            force=args.force,
        )
    except (OSError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(manifest, indent=2, sort_keys=True))
        return 0
    wrapped = ", ".join(manifest["wrapped_phases"])
    carried = sum(
        1 for item in manifest["entries"] if item["carried"] in {"copy", "symlink"}
    )
    print(f"capture toolchain: {manifest['toolchain']}")
    print(f"wrapped phases: {wrapped} (originals kept as <phase>.real)")
    print(
        f"carried: {carried} other entr(ies) by {manifest['carry_mode']}"
        + (
            f"; self-alias {', '.join(manifest['self_aliases'])} -> ."
            if manifest["self_aliases"]
            else ""
        )
    )
    print(f"captures: {manifest['captures']}")
    print(f"next: {manifest['usage']}")
    print(f"proof: {manifest['proof']}")
    return 0


def capture_runs_command(args: argparse.Namespace) -> int:
    try:
        report = list_capture_runs(
            args.destination,
            phase=args.phase,
            limit=None if args.all else args.limit,
        )
    except (OSError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0
    print(
        f"captures: {report['captures']} "
        f"({report['run_count']} run(s), {report['listed_count']} listed; "
        f"{report['phase_counts'] or 'none'})"
    )
    if not report["runs"]:
        print("no runs; build one translation unit through the capture toolchain")
    for run in report["runs"]:
        status = "-" if run["status"] is None else str(run["status"])
        print(
            f"{run['run_id']:<34s} {run['phase']:<8s} rc={status:<4s} "
            f"{_human_bytes(run['stream_bytes']):>7s} in "
            f"{run['file_count']:>2d} file(s)  {run['argv']['summary']}"
        )
    for item in report["unreadable"]:
        print(f"unreadable: {item['directory']}: {item['error']}", file=sys.stderr)
    return 0


def register_capture_commands(
    commands: argparse._SubParsersAction[Any],
) -> None:
    make = commands.add_parser(
        "capture-make",
        help="generate an arg-preserving capture toolchain around an IDO root",
        description=(
            "Wrap ugen/as0/as1 in one POSIX shell wrapper that retains every "
            "file argument before and after each invocation, so a normal build "
            "leaves the exact streams that crossed each pass boundary. The "
            "wrapper execs the untouched phase binary; the build's bytes do "
            "not change."
        ),
    )
    make.add_argument("ido_root", help="the unmodified IDO compiler directory")
    make.add_argument(
        "destination",
        help="where to write toolchain/ and captures/ (must not be inside the root)",
    )
    make.add_argument(
        "--phase",
        action="append",
        default=[],
        metavar="NAME",
        help=("phase to wrap; repeatable. Default: " + ", ".join(DEFAULT_PHASES)),
    )
    make.add_argument(
        "--link",
        action="store_true",
        help="symlink the carried binaries instead of copying them",
    )
    make.add_argument(
        "--force",
        action="store_true",
        help="replace an existing toolchain directory, keeping collected captures",
    )
    make.add_argument("--json", action="store_true", help="emit JSON")
    make.set_defaults(handler=capture_make_command)

    runs = commands.add_parser(
        "capture-runs",
        help="list the phase runs a capture toolchain collected",
        description=(
            "Read the run directories under a capture destination and report "
            "each run's phase, exit status, argv shape, and retained stream "
            "sizes. This command is static and runs no compiler."
        ),
    )
    runs.add_argument(
        "destination",
        help="a capture destination, or the captures directory itself",
    )
    runs.add_argument("--phase", help="list only runs of this phase")
    runs.add_argument(
        "--limit",
        type=int,
        default=20,
        help="show at most this many newest runs (default: 20)",
    )
    runs.add_argument("--all", action="store_true", help="show every run")
    runs.add_argument("--json", action="store_true", help="emit JSON")
    runs.set_defaults(handler=capture_runs_command)
