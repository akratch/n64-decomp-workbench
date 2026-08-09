"""Command journey for the shift-tolerant diff."""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from .cli_options import add_explain_keys_argument, add_symbol_argument
from .dis_cache import DisassemblyCache
from .model import Instruction, display_path, shorten_paths
from .row_source import load_dump_rows, load_object_rows
from .shift_align import (
    ALIGNMENT_GRANULARITIES,
    DEFAULT_GRANULARITY,
    ShiftDiff,
    build_shift_diff,
    shift_diff_lines,
)
from .terminal import add_terminal_arguments, emit_lines

__all__ = ["align_command", "register_align_commands"]

#: JSON identity for a multi-candidate run, which is a different shape from
#: one report and must not be confused with it by a consumer.
ALIGN_CENSUS_SCHEMA = "decomp-workbench-align-census-v1"


def parse_window(value: str) -> tuple[int, int]:
    """Parse ``LO..HI`` into an inclusive target row range."""

    text = value.strip()
    start, separator, stop = text.partition("..")
    if not separator:
        raise argparse.ArgumentTypeError(
            f"invalid --window {value!r}; write it as LO..HI, for example "
            "--window 2039..2110"
        )
    try:
        low, high = int(start), int(stop)
    except ValueError:
        raise argparse.ArgumentTypeError(
            f"invalid --window {value!r}; both bounds must be row numbers"
        ) from None
    if high < low:
        raise argparse.ArgumentTypeError(
            f"invalid --window {value!r}; the lower row comes first"
        )
    return low, high


def _rows(
    path: str, args: argparse.Namespace, *, cache: DisassemblyCache | None
) -> list[Instruction]:
    if getattr(args, "dumps", False):
        return load_dump_rows(path, symbol=args.symbol)
    return load_object_rows(
        path,
        objdump=args.objdump,
        symbol=args.symbol,
        section=args.section,
        cache=cache,
    )


def _window_tally(diff: ShiftDiff, window: tuple[int, int]) -> dict[str, int]:
    """Count insertions before and inside one target row window."""

    low, high = window
    before = sum(1 for row in diff.cuts if row < low)
    inside = sum(1 for row in diff.cuts if low <= row <= high)
    return {
        "window_start": low,
        "window_stop": high,
        "before": before,
        "inside": inside,
    }


def _census_lines(
    results: list[tuple[ShiftDiff, dict[str, int] | None]],
) -> list[str]:
    """One line per candidate, cheapest first: the batch reading."""

    labels, shared = shorten_paths([diff.candidate_name for diff, _ in results])
    width = max(len(labels[diff.candidate_name]) for diff, _ in results)
    header = (
        f"{'candidate'.ljust(width)}  {'rows':>5s} {'delta':>6s} {'away':>6s} "
        f"{'edit':>5s} {'rep':>5s} {'ins':>5s} {'del':>5s} {'residual':>8s}  shape"
    )
    if results and results[0][1] is not None:
        header += "  before  inside"
    lines = [header]
    for diff, window in sorted(
        results, key=lambda item: (item[0].rows_away, item[0].candidate_name)
    ):
        shape = (
            "aligned"
            if not diff.blocks
            else ("insertion-only" if diff.insertion_only else "structural")
        )
        line = (
            f"{labels[diff.candidate_name].ljust(width)}  {diff.candidate_rows:5d} "
            f"{diff.candidate_rows - diff.target_rows:+6d} {diff.rows_away:6d} "
            f"{diff.edit_distance:5d} {diff.replaced:5d} {diff.inserted:5d} "
            f"{diff.deleted:5d} {diff.paired_mismatches:8d}  {shape}"
        )
        if window is not None:
            line += f"  {window['before']:6d}  {window['inside']:6d}"
        lines.append(line)
    lines.append("")
    if shared:
        lines.append(shared)
    lines.append(
        "away = edit + residual: the instructions a source change must move. "
        "It is the ranking number; delta is how far the candidate's length is "
        "from the target's."
    )
    return lines


def align_command(args: argparse.Namespace) -> int:
    """Report how many instructions a candidate is away, not how far it shifted."""

    cache = (
        DisassemblyCache(args.disassembly_cache, objdump=args.objdump)
        if getattr(args, "disassembly_cache", None)
        else None
    )
    try:
        target = _rows(args.target, args, cache=cache)
        if not target:
            print(
                f"error: {display_path(args.target)} holds no instruction rows "
                "to align against; check --section and --symbol",
                file=sys.stderr,
            )
            return 2
        results: list[tuple[ShiftDiff, dict[str, int] | None]] = []
        for candidate in args.candidates:
            rows = _rows(candidate, args, cache=cache)
            diff = build_shift_diff(
                target,
                rows,
                target_name=display_path(args.target),
                candidate_name=display_path(candidate),
                symbol=args.symbol,
                granularity=args.align_on,
                context=args.context_rows,
            )
            window = _window_tally(diff, args.window) if args.window else None
            results.append((diff, window))
    except (OSError, RuntimeError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2

    notes = [f"cache: {event}" for event in (cache.rejections if cache else [])]
    if args.json:
        if len(results) == 1:
            payload: dict[str, Any] = results[0][0].as_dict()
            if results[0][1] is not None:
                payload["window"] = results[0][1]
        else:
            payload = {
                "schema": ALIGN_CENSUS_SCHEMA,
                "target": display_path(args.target),
                "candidates": [
                    {**diff.as_dict(), **({"window": window} if window else {})}
                    for diff, window in results
                ],
            }
        payload["cache_rejections"] = [
            event.as_dict()
            for event in (cache.events if cache else [])
            if event.status == "rejected"
        ]
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0

    if len(results) == 1:
        diff, window = results[0]
        lines = shift_diff_lines(diff, blocks=args.blocks)
        if window is not None:
            lines.append(
                f"window {window['window_start']}..{window['window_stop']}: "
                f"{window['before']} insertion(s) before it, "
                f"{window['inside']} inside it"
            )
    else:
        lines = _census_lines(results)
    if notes:
        lines.extend(("", *notes))
    emit_lines(lines, width=args.width, pager=args.pager)
    return 0


def _add_arguments(parser: argparse.ArgumentParser, *, object_inputs: bool) -> None:
    parser.add_argument(
        "--align-on",
        choices=ALIGNMENT_GRANULARITIES,
        default=DEFAULT_GRANULARITY,
        help=(
            "how much of each instruction the aligner sees: opcode "
            "(mnemonics only -- survives a register renaming, and the "
            "granularity a scorer wants), normalized (operand shape too), or "
            f"exact (default: {DEFAULT_GRANULARITY})"
        ),
    )
    parser.add_argument(
        "--window",
        type=parse_window,
        metavar="LO..HI",
        help=(
            "also tally how many insertions land before and inside this "
            "inclusive target row range, for example --window 2039..2110"
        ),
    )
    parser.add_argument(
        "--blocks",
        type=int,
        default=20,
        metavar="N",
        help="edit-script blocks to quote in the single-candidate report (default: 20)",
    )
    parser.add_argument(
        "--context-rows",
        type=int,
        default=3,
        metavar="N",
        help="instructions quoted from each side of a block (default: 3)",
    )
    add_symbol_argument(
        parser,
        help_text="align only this exact symbol; --function is the same option",
    )
    if object_inputs:
        parser.add_argument(
            "--section", default=".text", help="object section (default: .text)"
        )
        parser.add_argument(
            "--objdump",
            help="GNU-compatible MIPS objdump; auto-detected when omitted",
        )
        parser.add_argument(
            "--disassembly-cache",
            metavar="DIR",
            help=(
                "reuse disassemblies from this directory across runs; entries "
                "are rebuilt unless they prove they are a complete "
                "disassembly of the object on disk. There is no default: a "
                "scorer that defaults to a directory scores whatever is in it"
            ),
        )
    parser.add_argument(
        "--json",
        action="store_true",
        help=(
            "emit JSON. One candidate is a "
            "`decomp-workbench-shift-diff-v1` report; more than one is a "
            "`decomp-workbench-align-census-v1` document holding one such "
            "report per candidate under `candidates`. Switch on `schema`"
        ),
    )
    add_explain_keys_argument(parser)
    add_terminal_arguments(parser)


_DESCRIPTION = (
    "Report how many instructions a candidate is away from the target, "
    "rather than how far one insertion shifted it. Position-indexed "
    "comparison reads candidate row N against target row N, so an object "
    "that is byte-exact apart from one extra instruction reports a "
    "four-figure mismatch count and reads as garbage. This aligns the two "
    "streams and prints the edit script instead: replaced, inserted and "
    "deleted counts, the target rows each block lands at, and the derived "
    "cut list a banded scorer needs. Pass more than one candidate for a "
    "one-line-each census ordered by edit distance."
)


def register_align_commands(commands: argparse._SubParsersAction[Any]) -> None:
    """Register ``align`` and ``align-dumps``."""

    parser = commands.add_parser(
        "align",
        help="report the edit script between two objects, tolerant of shifts",
        description=_DESCRIPTION,
        epilog=(
            "example: decomp-workbench align target.o candidate.o --window 2039..2110"
        ),
    )
    parser.add_argument("target", help="reference object")
    parser.add_argument("candidates", nargs="+", help="candidate object(s)")
    _add_arguments(parser, object_inputs=True)
    parser.set_defaults(handler=align_command, dumps=False, report_command="align")

    dumps = commands.add_parser(
        "align-dumps",
        help="align retained objdump text instead of objects",
        description=_DESCRIPTION
        + " This variant reads retained `objdump -d -r` text, for a reader "
        "who has the dumps but not the objects.",
    )
    dumps.add_argument("target", help="retained target disassembly")
    dumps.add_argument("candidates", nargs="+", help="retained candidate disassembly")
    _add_arguments(dumps, object_inputs=False)
    dumps.set_defaults(
        handler=align_command,
        dumps=True,
        objdump=None,
        section=".text",
        disassembly_cache=None,
        report_command="align-dumps",
    )
