"""Command journey for the measured force-control to object-row join."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from .cli_options import add_explain_keys_argument, add_symbol_argument
from .force_rows import DEFAULT_GAP, build_force_rows, force_rows_lines
from .instrument_uopt import parse_force_specification
from .model import Instruction, display_path
from .objdump import dump_object, parse_disassembly, symbol_selection_error
from .terminal import add_terminal_arguments, emit_lines

__all__ = ["force_rows_command", "register_force_rows_commands"]


def _load(
    path: str, args: argparse.Namespace, *, symbol: str | None
) -> list[Instruction]:
    """Read one side, from an object or from retained objdump text."""

    if getattr(args, "objdump", None) is not None or hasattr(args, "section"):
        _, instructions = dump_object(
            path, objdump=args.objdump, symbol=symbol, section=args.section
        )
        return list(instructions)
    text = Path(path).read_text(encoding="utf-8")
    instructions = parse_disassembly(text, symbol=symbol)
    if not instructions:
        raise ValueError(
            symbol_selection_error(symbol, inputs=((display_path(path), text),))
        )
    return list(instructions)


def force_rows_command(args: argparse.Namespace) -> int:
    """Report the object rows one allocator force control moved."""

    try:
        # The same parser the pass itself uses. A control this command accepts
        # is a control the instrumented profile accepts, so a run cannot be
        # labelled with a force string that never applied.
        parse_force_specification(args.force)
        symbol = getattr(args, "symbol", None)
        baseline = _load(args.baseline, args, symbol=symbol)
        forced = _load(args.forced, args, symbol=symbol)
        target = (
            _load(args.target, args, symbol=symbol)
            if getattr(args, "target", None)
            else None
        )
        result = build_force_rows(
            baseline,
            forced,
            force=args.force,
            baseline_name=display_path(args.baseline),
            forced_name=display_path(args.forced),
            target=target,
            target_name=display_path(args.target) if args.target else None,
            symbol=symbol,
            gap=args.gap,
        )
    except (OSError, RuntimeError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(result.as_dict(), indent=2, sort_keys=True))
        return 0
    emit_lines(force_rows_lines(result), width=args.width, pager=args.pager)
    return 0


def _add_arguments(parser: argparse.ArgumentParser, *, object_inputs: bool) -> None:
    parser.add_argument(
        "--force",
        required=True,
        metavar="CONTROL",
        help=(
            "the phase-qualified control the forced build was made with, such "
            "as p1:w9=c30; validated by the same parser the instrumented pass "
            "uses, and recorded in the report"
        ),
    )
    parser.add_argument(
        "--target",
        help=(
            "optional reference object; joins every run to the aligned row "
            "`compare --json` and `window` publish"
        ),
    )
    parser.add_argument(
        "--gap",
        type=int,
        default=DEFAULT_GAP,
        help=(
            "matched rows tolerated inside one run before it is split "
            f"(default: {DEFAULT_GAP}; 0 reports strictly contiguous runs)"
        ),
    )
    add_symbol_argument(
        parser,
        help_text="measure only this exact symbol; --function is the same option",
    )
    if object_inputs:
        parser.add_argument(
            "--section", default=".text", help="object section (default: .text)"
        )
        parser.add_argument(
            "--objdump",
            help="GNU-compatible MIPS objdump; auto-detected when omitted",
        )
    add_explain_keys_argument(parser)
    parser.add_argument("--json", action="store_true", help="emit JSON")
    add_terminal_arguments(parser)


def register_force_rows_commands(commands: argparse._SubParsersAction[Any]) -> None:
    """Register ``force-rows`` and ``force-rows-dumps``."""

    description = (
        "Measure which object rows one allocator force control owns. Build "
        "the same source twice -- once without the control and once with it "
        "-- and this reports the rows that moved, grouped into runs and "
        "joined to the aligned row numbers `compare --json` publishes. It "
        "builds nothing itself: the two objects are inputs, so the join works "
        "for any control a reader can set."
    )
    parser = commands.add_parser(
        "force-rows",
        help="join an allocator force control to the object rows it moved",
        description=description,
    )
    parser.add_argument("baseline", help="object built without the control")
    parser.add_argument("forced", help="object built with the control")
    _add_arguments(parser, object_inputs=True)
    parser.set_defaults(handler=force_rows_command, report_command="force-rows")

    dumps = commands.add_parser(
        "force-rows-dumps",
        help="join a force control to object rows from retained objdump text",
        description=description,
    )
    dumps.add_argument("baseline", help="objdump text of the unforced build")
    dumps.add_argument("forced", help="objdump text of the forced build")
    _add_arguments(dumps, object_inputs=False)
    dumps.set_defaults(handler=force_rows_command, report_command="force-rows-dumps")
