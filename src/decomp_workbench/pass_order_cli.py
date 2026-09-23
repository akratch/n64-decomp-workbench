"""Command journey for the pass-order model: `pass order`."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any

from .campaign import run_compiler
from .command_line import split_command
from .environment import parse_environment
from .pass_order import parse_annotations, pass_order_report

__all__ = ["register_pass_order_command"]


def compile_listing(
    source: Path,
    template: str,
    *,
    environment: dict[str, str],
    timeout: float | None,
) -> tuple[str, list[str]]:
    """Compile a mini TU with `cc -S` in a private directory; return the listing.

    IDO's `cc -S` writes `<stem>.s` into its working directory and ignores
    `-o`, so the compile runs in a fresh directory holding a copy of the
    source, and nothing lands beside the caller's files.
    """

    parts = split_command(template)
    if not any("{source}" in part for part in parts):
        raise ValueError("--compile-command must contain {source}")
    with tempfile.TemporaryDirectory(prefix="dkwb-pass-order-") as scratch:
        work = Path(scratch)
        copy = work / source.name
        shutil.copyfile(source, copy)
        command = [part.replace("{source}", str(copy)) for part in parts]
        completed = run_compiler(
            command, environment=environment, compile_cwd=work, timeout=timeout
        )
        if completed.returncode != 0:
            raise RuntimeError(
                f"the mini TU failed to compile (exit {completed.returncode}): "
                f"{completed.stderr[-2048:]}"
            )
        listing = work / f"{source.stem}.s"
        if not listing.is_file():
            found = sorted(work.glob("*.s"))
            if len(found) != 1:
                raise RuntimeError(
                    f"no {listing.name} after the compile; pass -S in --compile-command"
                )
            listing = found[0]
        return listing.read_text(encoding="utf-8", errors="replace"), command


def _lines(report: dict[str, Any]) -> list[str]:
    lines = [
        f"pass order: {report['source']}  "
        + ("model checked against the listing" if report["observed"] else "model only")
    ]
    for row in report["statements"]:
        variable = row["variable"] or ""
        observed = (
            f"  observed {row['observed']}" if row["observed"] is not None else ""
        )
        flag = {True: "", False: "  UNEXPLAINED", None: ""}[row["agrees"]]
        lines.append(
            f"  line {row['line']:>4} bb={row['block']:<5} {row['role']:<7} "
            f"{variable:<6} -> {row['predicted']:<14} {row['law']} "
            f"{row['rule']}{observed}{flag}"
        )
        for note in row["notes"]:
            lines.append(f"         note: {note}")
    if report["unexplained"]:
        lines.append(
            "unexplained line(s): "
            + ", ".join(map(str, report["unexplained"]))
            + " -- the listing is the measurement; the model does not describe "
            "this mini TU there"
        )
    lines.append(f"boundary: {report['boundary']}")
    return lines


def pass_order_command(args: argparse.Namespace) -> int:
    try:
        source = Path(args.source).expanduser()
        statements = parse_annotations(source.read_text(encoding="utf-8"))
        listing = None
        command = None
        if args.listing and args.compile_command:
            raise ValueError("pass --listing or --compile-command, not both")
        if args.listing:
            listing = (
                Path(args.listing)
                .expanduser()
                .read_text(encoding="utf-8", errors="replace")
            )
        elif args.compile_command:
            environment = {"PATH": os.environ.get("PATH", "")}
            environment.update(parse_environment(args.env))
            listing, command = compile_listing(
                source.resolve(),
                args.compile_command,
                environment=environment,
                timeout=args.timeout,
            )
        report = pass_order_report(
            statements,
            listing=listing,
            symbol=args.symbol,
            source_name=source.name,
            compile_command=command,
        )
    except (OSError, RuntimeError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print("\n".join(_lines(report)))
    return 1 if report["unexplained"] else 0


def register_pass_order_command(commands: argparse._SubParsersAction[Any]) -> None:
    """Register `pass-order` behind the `pass order` spelling."""

    parser = commands.add_parser(
        "pass-order",
        help=argparse.SUPPRESS,
        description=(
            "Replay uopt's measured pass-order rules (L162-L167) over a mini "
            "TU's @pass-annotated statements, naming the rule that decides "
            "each one, and with --listing or --compile-command check each "
            "def's predicted fate against what its line emitted in the cc -S "
            "listing. Exit 1 when a def's observed fate is unexplained."
        ),
        epilog=(
            "example: decomp-workbench pass order "
            "examples/fixtures/pass-order-mini.c --listing "
            "examples/fixtures/pass-order-mini.s"
        ),
    )
    parser.add_argument("source", help="the annotated mini TU")
    parser.add_argument("--listing", help="its cc -S listing")
    parser.add_argument(
        "--compile-command",
        help="compile it: a template with {source} and -S, run in a private directory",
    )
    parser.add_argument("--env", action="append", default=[], metavar="NAME=VALUE")
    parser.add_argument("--timeout", type=float, default=60.0)
    parser.add_argument("--symbol", help="the listing function to read")
    parser.add_argument("--json", action="store_true", help="emit JSON")
    parser.set_defaults(handler=pass_order_command, report_command="pass-order")
