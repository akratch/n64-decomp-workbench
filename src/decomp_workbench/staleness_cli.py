"""CLI for the build-freshness guard: `check-staleness`, and the shared options.

The command is the host-facing half of `staleness.staleness_report`: a wrapper
script that rebuilds a ROM and then compares it can ask, in one line and
without parsing anything, whether the image it is about to trust is newer than
the source that was edited. The options are the comparison-facing half, added
to every command that reports on an artifact somebody just built.
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from .staleness import (
    DEFAULT_TOLERANCE_SECONDS,
    STALENESS_SCHEMA,
    StaleBuildError,
    StalenessReport,
    chain_report,
    enforce_freshness,
    staleness_report,
)

_DESCRIPTION = (
    "Check a build chain named in build order, earliest input first. Every "
    "earlier path is treated as an input to every later one, so a ROM that "
    "was relinked after its object but before the source was recompiled is "
    "reported stale against the source. Exit status is 0 when every artifact "
    "is at least as new as the inputs before it, and 1 otherwise -- including "
    "when a path is missing, because an unproven chain is not a fresh one."
)

_EPILOG = (
    "example: decomp-workbench check-staleness src/track.c build/track.o "
    "build/game.elf build/game.z64"
)


def add_freshness_arguments(parser: argparse.ArgumentParser) -> None:
    """Add `--built-from` and `--allow-stale` to a comparison command.

    Both spellings exist because the guard has to be both loud and passable:
    the refusal is the default (a stale comparison reads as a match, which is
    the expensive way to be wrong), and the escape hatch is one flag away for
    the operator who is deliberately comparing against a retained build.
    """

    parser.add_argument(
        "--built-from",
        action="append",
        metavar="PATH",
        help=(
            "an input the compared artifacts were built from -- the source, "
            "the object, the ELF. Repeatable. The command refuses when a "
            "compared artifact is older than one of these"
        ),
    )
    parser.add_argument(
        "--allow-stale",
        action="store_true",
        help=(
            "report the staleness and continue anyway, instead of refusing. "
            "The report is printed either way"
        ),
    )


def freshness_report(
    args: argparse.Namespace,
    *derived: str,
    labels: tuple[str, ...] = (),
) -> StalenessReport:
    """Build the report for one comparison's own inputs and outputs."""

    inputs = tuple(getattr(args, "built_from", None) or ())
    input_labels = tuple(
        f"source{index + 1}" if len(inputs) > 1 else "source"
        for index in range(len(inputs))
    )
    return chain_report(
        derived,
        inputs,
        labels=(*input_labels, *labels) if labels else None,
    )


def guard_freshness(
    args: argparse.Namespace,
    *derived: str,
    labels: tuple[str, ...] = (),
) -> tuple[StalenessReport, list[str]]:
    """Return the report and its warnings, refusing a stale build by default.

    Raises `StaleBuildError`, which every comparison command already handles
    as a `ValueError`: the refusal reaches the terminal as `error: ...` and
    `--json` as the standard error document, with no per-command plumbing.
    """

    report = freshness_report(args, *derived, labels=labels)
    warnings = enforce_freshness(
        report, allow_stale=bool(getattr(args, "allow_stale", False))
    )
    return report, warnings


def freshness_display(
    args: argparse.Namespace,
    *derived: str,
    labels: tuple[str, ...] = (),
) -> tuple[StalenessReport, list[str]]:
    """Return the report and its warnings for a command that already ran.

    Never raises. The refusal belongs at the top of the handler, before the
    objdump; by the time a report is being rendered the decision to continue
    has been made, and this half only has to say what was compared and when
    it was built.
    """

    report = freshness_report(args, *derived, labels=labels)
    if not report.stale:
        return report, []
    return report, enforce_freshness(report, allow_stale=True)


def freshness_payload(report: StalenessReport) -> dict[str, Any]:
    """Render the report as a namespaced sub-document.

    A merged block names itself under a prefixed key and never rewrites its
    host's `schema`, so a consumer switching on `schema` still knows it is
    holding a comparison.
    """

    body = {key: value for key, value in report.as_dict().items() if key != "schema"}
    return {"staleness": body, "staleness_schema": STALENESS_SCHEMA}


def _tolerance(value: str) -> float:
    """Parse `--tolerance`, refusing a negative slack window.

    A negative tolerance is not a stricter check: it makes an artifact that
    is *newer* than its input stale, so a correct build reports as stale and
    the reader learns to ignore the verdict. That is the same false answer
    this command exists to prevent, pointed the other way.
    """

    try:
        seconds = float(value)
    except ValueError:
        raise argparse.ArgumentTypeError(f"{value!r} is not a number") from None
    if seconds != seconds or seconds < 0:  # NaN compares false with itself
        raise argparse.ArgumentTypeError(
            "--tolerance is a slack window in seconds and must not be "
            f"negative; got {value!r}"
        )
    return seconds


def check_staleness_command(args: argparse.Namespace) -> int:
    if len(args.paths) < 2:
        print(
            "error: name at least two paths in build order; one artifact has "
            "nothing to be older than",
            file=sys.stderr,
        )
        return 2
    labels = tuple(args.label or ())
    if labels and len(labels) != len(args.paths):
        print(
            f"error: {len(args.paths)} path(s) and {len(labels)} --label(s); "
            "they must correspond",
            file=sys.stderr,
        )
        return 2
    report = staleness_report(
        *args.paths,
        labels=labels or None,
        hashes=args.sha256,
        tolerance_seconds=args.tolerance,
    )
    if args.json:
        print(json.dumps(report.as_dict(), indent=2, sort_keys=True))
    else:
        print("\n".join(report.lines()))
    if report.stale and args.allow_stale:
        return 0
    return 0 if report.fresh else 1


def register_staleness_command(commands: argparse._SubParsersAction[Any]) -> None:
    """Register `check-staleness`."""

    parser = commands.add_parser(
        "check-staleness",
        help="refuse to trust a build older than the inputs it came from",
        description=_DESCRIPTION,
        epilog=_EPILOG,
    )
    parser.add_argument(
        "paths",
        nargs="+",
        help="artifacts in build order: source, object, ELF, ROM",
    )
    parser.add_argument(
        "--label",
        action="append",
        metavar="NAME",
        help="name one row of the report; repeat once per path",
    )
    parser.add_argument(
        "--sha256",
        action="store_true",
        help="record each artifact's content hash, so a host can compare runs",
    )
    parser.add_argument(
        "--tolerance",
        type=_tolerance,
        default=DEFAULT_TOLERANCE_SECONDS,
        metavar="SECONDS",
        help=(
            "how much older a derived artifact may be before it is stale "
            f"(default: {DEFAULT_TOLERANCE_SECONDS}, one filesystem "
            "timestamp tick)"
        ),
    )
    parser.add_argument(
        "--allow-stale",
        action="store_true",
        help="report the staleness but exit 0 anyway",
    )
    parser.add_argument("--json", action="store_true", help="emit JSON")
    parser.set_defaults(
        handler=check_staleness_command, report_command="check-staleness"
    )


__all__ = [
    "StaleBuildError",
    "add_freshness_arguments",
    "check_staleness_command",
    "freshness_display",
    "freshness_payload",
    "freshness_report",
    "guard_freshness",
    "register_staleness_command",
]
