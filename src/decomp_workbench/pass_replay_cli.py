"""CLI for replaying a retained Ucode stream through stock ugen and as1."""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from .pass_replay import replay_ugen


def _environment(values: list[str]) -> dict[str, str]:
    environment: dict[str, str] = {}
    for item in values:
        name, separator, value = item.partition("=")
        if not separator or not name:
            raise ValueError(f"--env wants NAME=VALUE, got {item!r}")
        environment[name] = value
    return environment


def replay_ugen_command(args: argparse.Namespace) -> int:
    try:
        report = replay_ugen(
            args.ucode,
            toolchain=args.toolchain,
            argv_from=args.argv_from,
            output=args.output,
            as1_argv_from=args.as1_argv_from,
            expect=args.expect,
            run_as1=not args.skip_as1,
            keep_work=args.keep_work,
            work_root=args.work_root,
            compile_cwd=args.compile_cwd,
            environment=_environment(args.env),
            timeout=args.timeout,
            nice=args.nice,
            objdump=args.objdump,
        )
    except (OSError, RuntimeError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(
            f"ucode: {report['ucode']['bytes']} bytes, "
            f"sha256={report['ucode']['sha256'][:12]}"
        )
        print(f"argv from: {report['argv_source']['ugen_run']}")
        if report["argv_source"]["as1_run"]:
            print(
                f"as1 argv:  {report['argv_source']['as1_run']} "
                f"({report['argv_source']['as1_discovery']})"
            )
        print(
            f"binasm: {report['binasm']['bytes']} bytes, "
            f"sha256={report['binasm']['sha256'][:12]}"
        )
        for warning in report.get("warnings", []):
            print(f"warning: {warning}", file=sys.stderr)
        if "object" in report:
            print(
                f"object: {report['object']['bytes']} bytes, "
                f"sha256={report['object']['sha256'][:12]}"
                + (
                    f" -> {report['object']['path']}"
                    if report["object"].get("path")
                    else ""
                )
            )
            verification = report["verification"]
            print(f"verify: {verification['verdict']}")
            if verification.get("reference"):
                print(f"  reference: {verification['reference']}")
        print(f"proof: {report['proof']}")
    verification = report.get("verification") or {}
    if args.require_identical and verification.get("byte_identical") is not True:
        return 1
    return 0


def register_replay_ugen_command(
    commands: argparse._SubParsersAction[Any],
) -> None:
    parser = commands.add_parser(
        "replay-ugen",
        help="replay a Ucode stream through stock ugen and as1 with captured argv",
        description=(
            "Run one retained or patched binary Ucode stream through the stock "
            "ugen and as1 binaries, reusing the exact argument shape a capture "
            "run recorded -- including the -t symbol table, which ugen mutates "
            "and as1 then reads. Replaying a capture's own unmodified Ucode "
            "must reproduce that capture's object byte for byte; until it "
            "does, a patched variant's difference is not attributable to the "
            "patch."
        ),
    )
    parser.add_argument("ucode", help="the Ucode stream to replay")
    parser.add_argument(
        "--toolchain",
        required=True,
        help="a capture destination or IDO root; <phase>.real is preferred",
    )
    parser.add_argument(
        "--argv-from",
        required=True,
        metavar="RUN_DIR",
        help="the ugen capture run whose argument shape to reuse",
    )
    parser.add_argument(
        "--as1-argv-from",
        metavar="RUN_DIR",
        help=(
            "the as1 capture run to reuse; by default the run whose positional "
            "input is this ugen run's -o file"
        ),
    )
    parser.add_argument("-o", "--output", help="write the replayed object here")
    parser.add_argument(
        "--expect",
        help="verify against this object instead of the as1 run's retained one",
    )
    parser.add_argument(
        "--skip-as1",
        action="store_true",
        help="stop after ugen and produce only the Binasm stream",
    )
    parser.add_argument(
        "--require-identical",
        action="store_true",
        help="exit 1 unless the replayed object matches the reference exactly",
    )
    parser.add_argument("--keep-work", help="retain the replay intermediates here")
    parser.add_argument(
        "--work-root",
        help="project-visible parent for the temporary work directory",
    )
    parser.add_argument(
        "--compile-cwd",
        default=".",
        help="working directory for each phase (default: .)",
    )
    parser.add_argument(
        "--env",
        action="append",
        default=[],
        metavar="NAME=VALUE",
        help="add or override one environment variable; repeatable",
    )
    parser.add_argument(
        "--nice",
        type=int,
        default=10,
        help="run each phase at this nice level (default: 10)",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=300.0,
        help="per-phase timeout in seconds (default: 300)",
    )
    parser.add_argument("--objdump", help="objdump used to explain a mismatch")
    parser.add_argument("--json", action="store_true", help="emit JSON")
    parser.set_defaults(handler=replay_ugen_command)
