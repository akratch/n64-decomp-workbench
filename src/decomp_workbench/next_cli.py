"""CLI for `next`: discovery as a command instead of folklore."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from .cli_options import add_symbol_argument
from .compare import compare_instructions, compare_objects
from .model import Comparison, display_path
from .objdump import cross_function_warning, parse_disassembly, symbol_selection_error
from .whats_next import plan_next_steps, render_plan

#: How many steps a default run prints. Enough to act on, short enough that
#: the first one is obviously the first one.
DEFAULT_LIMIT = 3


def _compare_dumps(target: str, candidate: str, *, symbol: str | None) -> Comparison:
    """Compare two retained objdump texts, the same way `compare-dumps` does."""

    target_text = Path(target).read_text(encoding="utf-8")
    candidate_text = Path(candidate).read_text(encoding="utf-8")
    target_items = parse_disassembly(target_text, symbol=symbol)
    candidate_items = parse_disassembly(candidate_text, symbol=symbol)
    if not target_items or not candidate_items:
        raise ValueError(
            symbol_selection_error(
                symbol,
                inputs=(
                    (display_path(target), target_text),
                    (display_path(candidate), candidate_text),
                ),
            )
        )
    warning = cross_function_warning(target_text, candidate_text, symbol=symbol)
    return compare_instructions(
        target_items,
        candidate_items,
        target_name=display_path(target),
        candidate_name=display_path(candidate),
        symbol=symbol,
        warnings=(warning,) if warning else (),
    )


def next_command(args: argparse.Namespace) -> int:
    try:
        if getattr(args, "dumps", False):
            comparison = _compare_dumps(args.target, args.candidate, symbol=args.symbol)
        else:
            comparison = compare_objects(
                args.target,
                args.candidate,
                objdump=args.objdump,
                symbol=args.symbol,
                section=args.section,
            )
    except (OSError, RuntimeError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    if comparison.error:
        print(f"error: {comparison.error}", file=sys.stderr)
        return 2
    plan = plan_next_steps(
        comparison,
        target=args.target,
        candidate=args.candidate,
        source=args.src,
    )
    if args.json:
        payload: dict[str, Any] = plan.as_dict()
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        limit = None if args.all else DEFAULT_LIMIT
        print("\n".join(render_plan(plan, limit=limit)))
    return 0


_DESCRIPTION = (
    "Read the current comparison state and print the next diagnostic step "
    "or steps, in priority order, each as a runnable command with the real "
    "paths already substituted and one sentence saying what it settles. "
    "Steps that clear a blocker -- a difference that makes the others "
    "unreadable, such as an instruction-count delta -- rank above steps that "
    "interpret what the blocker distorts. The lever detail stays in `guide`, "
    "which every plan ends by naming."
)


def _add_common_arguments(parser: argparse.ArgumentParser) -> None:
    add_symbol_argument(
        parser, help_text="compare only this function, selected from both inputs"
    )
    parser.add_argument(
        "--src",
        metavar="FILE",
        help="the candidate's C source, so region attribution names a real path",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help=f"print every step, not just the first {DEFAULT_LIMIT}",
    )
    parser.add_argument("--json", action="store_true", help="emit JSON")


def register_next_command(commands: argparse._SubParsersAction[Any]) -> None:
    parser = commands.add_parser(
        "next",
        help="name the next diagnostic step, with the command and why",
        description=_DESCRIPTION,
        epilog=("example: decomp-workbench next target.o candidate.o --src work.c"),
    )
    parser.add_argument("target", help="target object (.o)")
    parser.add_argument("candidate", help="candidate object (.o)")
    _add_common_arguments(parser)
    parser.add_argument(
        "--objdump", help="GNU-compatible MIPS objdump; auto-detected when omitted"
    )
    parser.add_argument(
        "--section", default=".text", help="object section (default: .text)"
    )
    parser.set_defaults(handler=next_command, dumps=False)

    dumps = commands.add_parser(
        "next-dumps",
        help=argparse.SUPPRESS,
        description=_DESCRIPTION + " Reads two retained objdump texts.",
    )
    dumps.add_argument("target", help="retained target disassembly text")
    dumps.add_argument("candidate", help="retained candidate disassembly text")
    _add_common_arguments(dumps)
    dumps.set_defaults(handler=next_command, dumps=True, objdump=None, section=".text")
