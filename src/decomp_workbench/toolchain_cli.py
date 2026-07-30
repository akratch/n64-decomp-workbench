"""CLI for real-copy external toolchain setup and health."""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from .toolchain import calibrate_toolchain, initialize_toolchain, toolchain_status


def _named(values: list[str], *, option: str) -> dict[str, str]:
    result = {}
    for value in values:
        name, separator, path = value.partition("=")
        if not separator or not name or not path:
            raise ValueError(f"{option} expects RELATIVE_PATH=SOURCE: {value!r}")
        if name in result:
            raise ValueError(f"{option} repeats {name!r}")
        result[name] = path
    return result


def _pairs(
    values: list[str],
    *,
    option: str = "--fidelity-pair",
) -> list[tuple[str, str]]:
    result = []
    for value in values:
        stock, separator, instrumented = value.partition("=")
        if not separator or not stock or not instrumented:
            raise ValueError(f"{option} expects LEFT=RIGHT: {value!r}")
        result.append((stock, instrumented))
    return result


def toolchain_init_command(args: argparse.Namespace) -> int:
    try:
        replacements = _named(args.replace, option="--replace")
        for relative, source in (("uopt", args.uopt), ("ugen", args.ugen)):
            if source is None:
                continue
            if relative in replacements:
                raise ValueError(
                    f"--{relative} and --replace {relative}=... are mutually exclusive"
                )
            replacements[relative] = source
        report = initialize_toolchain(
            args.destination,
            base=args.base,
            replacements=replacements,
            fidelity_pairs=_pairs(args.fidelity_pair),
            scheduler_positive_log=args.scheduler_positive_log,
            objdump=args.objdump,
        )
    except (OSError, RuntimeError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(f"toolchain: {report['claim'].upper()} ({report['directory']})")
        print("gates:")
        for name, passed in report["gates"].items():
            print(f"  {name}: {'PASS' if passed else 'NOT RUN'}")
        if report["claim"] != "ready":
            # "finish every fidelity gate" named a state, not a command. The
            # reader who lands here is usually the reader a register verdict
            # sent looking for instrumentation, so give both the gate command
            # and the source-only route that needs no toolchain at all.
            print(
                "next: finish every fidelity gate before treating traces as "
                "supported evidence"
            )
            print(
                "      run the gates: decomp-workbench toolchain calibrate "
                f"{report['directory']} (see docs/toolchain-calibration.md)"
            )
            print(
                "      no instrumented toolchain yet? the source-only levers "
                "still apply: decomp-workbench guide pool-position"
            )
    return 0


def toolchain_calibrate_command(args: argparse.Namespace) -> int:
    try:
        report = calibrate_toolchain(
            args.directory,
            unedited_replay_pairs=_pairs(
                args.unedited_replay_pair,
                option="--unedited-replay-pair",
            ),
            collateral_pairs=_pairs(
                args.collateral_pair,
                option="--collateral-pair",
            ),
            project_output_pairs=_pairs(
                args.project_output_pair,
                option="--project-output-pair",
            ),
            scheduler_positive_log=args.scheduler_positive_log,
            objdump=args.objdump,
        )
    except (OSError, RuntimeError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(f"toolchain: {report['claim'].upper()} ({report['directory']})")
        for name, passed in report["gates"].items():
            print(f"  {name}: {'PASS' if passed else 'NOT RUN'}")
        if report["next_missing_gates"]:
            print("next missing gates: " + ", ".join(report["next_missing_gates"]))
    # The command succeeded when every supplied calibration cell was valid and
    # durably recorded.  A partially calibrated toolchain is a state, not a
    # command failure; scripts can inspect ``claim`` or ``next_missing_gates``
    # without conflating "more evidence required" with a broken invocation.
    return 0


def toolchain_status_command(args: argparse.Namespace) -> int:
    try:
        report = toolchain_status(args.directory)
    except (OSError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(f"toolchain: {report['claim'].upper()} ({report['directory']})")
        print(f"integrity: {'PASS' if report['integrity'] else 'FAIL'}")
        if report["next_missing_gates"]:
            print("missing gates: " + ", ".join(report["next_missing_gates"]))
    return 0 if report["integrity"] else 1


def register_toolchain_commands(
    commands: argparse._SubParsersAction[Any],
) -> None:
    init = commands.add_parser(
        "toolchain-init",
        help=argparse.SUPPRESS,
        description=(
            "Materialize a real-copy external toolchain and record hashes and "
            "calibration gates. No compiler binaries enter this repository."
        ),
    )
    init.add_argument("destination")
    init.add_argument("--base", required=True)
    init.add_argument("--uopt", help="instrumented uopt copied to BASE/uopt")
    init.add_argument("--ugen", help="instrumented ugen copied to BASE/ugen")
    init.add_argument(
        "--replace",
        action="append",
        default=[],
        metavar="RELATIVE_PATH=SOURCE",
    )
    init.add_argument(
        "--fidelity-pair",
        action="append",
        default=[],
        metavar="STOCK=INSTRUMENTED_OFF",
    )
    init.add_argument("--scheduler-positive-log")
    init.add_argument("--objdump")
    init.add_argument("--json", action="store_true", help="emit JSON")
    init.set_defaults(handler=toolchain_init_command)

    calibrate = commands.add_parser(
        "toolchain-calibrate",
        help=argparse.SUPPRESS,
        description=(
            "Run missing calibration cells. Object pairs use section-scoped "
            "fidelity; project outputs require exact file identity."
        ),
    )
    calibrate.add_argument("directory")
    calibrate.add_argument(
        "--unedited-replay-pair",
        action="append",
        default=[],
        metavar="NORMAL=REPLAY",
    )
    calibrate.add_argument(
        "--collateral-pair",
        action="append",
        default=[],
        metavar="STOCK=INSTRUMENTED_OFF",
    )
    calibrate.add_argument(
        "--project-output-pair",
        action="append",
        default=[],
        metavar="EXPECTED=ACTUAL",
    )
    calibrate.add_argument("--scheduler-positive-log")
    calibrate.add_argument("--objdump")
    calibrate.add_argument("--json", action="store_true", help="emit JSON")
    calibrate.set_defaults(handler=toolchain_calibrate_command)

    status = commands.add_parser(
        "toolchain-status",
        help=argparse.SUPPRESS,
        description="Verify toolchain hashes and summarize calibration claims.",
    )
    status.add_argument("directory")
    status.add_argument("--json", action="store_true", help="emit JSON")
    status.set_defaults(handler=toolchain_status_command)
