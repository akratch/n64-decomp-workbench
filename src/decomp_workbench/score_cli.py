"""CLI for `score`: byte-exact function scoring against ROM or object truth."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from .cli_options import add_symbol_argument
from .score import (
    ScoreError,
    ScoreReport,
    ScoreSpec,
    TargetSpec,
    WordScore,
    parse_control_spec,
    score_report,
)

NEXT_GUIDE = "decomp-workbench guide"
NEXT_DIAGNOSE = "decomp-workbench diagnose"


def score_spec_from_args(args: argparse.Namespace) -> ScoreSpec:
    """Translate parsed CLI arguments into a `ScoreSpec`, validating combinations."""

    function = args.symbol
    between: tuple[str, str] | None = None
    if args.between:
        parts = [item.strip() for item in args.between.split(",")]
        if len(parts) != 2 or not all(parts):
            raise ScoreError(
                f"--between expects SYMA,SYMB (two symbol names): got {args.between!r}"
            )
        between = (parts[0], parts[1])
    if bool(function) == bool(between):
        raise ScoreError(
            "pass exactly one of --function/--symbol or --between to select "
            "the candidate function"
        )
    if bool(args.target_object) == bool(args.rom):
        raise ScoreError(
            "pass exactly one of --target-object or --rom to supply target bytes"
        )
    if args.rom:
        if not args.rom_offset:
            raise ScoreError("--rom requires --rom-offset")
        try:
            rom_offset = int(args.rom_offset, 0)
        except ValueError as error:
            raise ScoreError(
                f"--rom-offset is not a valid integer: {args.rom_offset!r}"
            ) from error
        target = TargetSpec(
            kind="rom", rom=args.rom, rom_offset=rom_offset, size=args.size
        )
    else:
        if args.size is not None:
            raise ScoreError("--size only applies together with --rom")
        target = TargetSpec(kind="object", target_object=args.target_object)
    controls = tuple(parse_control_spec(item) for item in args.control)
    return ScoreSpec(
        target=target,
        function=function,
        between=between,
        controls=controls,
        objdump=args.objdump,
        section=args.section,
    )


def print_guidance(lines: list[str]) -> None:
    for position, entry in enumerate(lines):
        prefix = "next: " if position == 0 else "      "
        print(f"{prefix}{entry}")


def _print_word_score(item: WordScore, *, indent: str = "") -> None:
    print(f"{indent}{item.label} ({item.mode}): {item.summary}")
    if item.note:
        print(f"{indent}  note: {item.note}")


def render_score_human(report: ScoreReport) -> None:
    print(f"candidate: {report.candidate}")
    print(f"target: {report.target_description}")
    _print_word_score(report.function)
    if report.controls:
        print(f"controls: {len(report.controls)} checked")
        for control in report.controls:
            state = "OK" if control.matched else "BROKEN"
            print(f"  {control.label} ({control.mode}): {control.summary} {state}")
    verdict = "MATCH" if report.matched else "MISMATCH"
    if report.controls_broken:
        verdict += " (CONTROLS BROKEN)"
    print(f"verdict: {verdict}")
    print_guidance(report.guidance)


def score_command(args: argparse.Namespace) -> int:
    try:
        spec = score_spec_from_args(args)
        candidate = Path(args.candidate)
        report = score_report(candidate, spec)
    except (ScoreError, OSError, RuntimeError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    if args.json:
        payload: dict[str, Any] = {
            "schema": "decomp-workbench-score-v1",
            **report.as_dict(),
        }
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        render_score_human(report)
    return 0 if report.matched else 1


def register_score_command(commands: Any) -> None:
    parser = commands.add_parser(
        "score",
        help="score a candidate function's bytes against ROM or object truth",
        description=(
            "Extract one function's instruction words from a candidate "
            "object, mask linker-controlled relocation fields, and compare "
            "them word-for-word against target bytes read from a ROM offset "
            "or a target object. Repeatable --control functions catch a "
            "lever that changed something it must not touch."
        ),
    )
    parser.add_argument("candidate", help="candidate object (.o)")
    add_symbol_argument(
        parser,
        help_text="score only this function, selected from the symbol table",
    )
    parser.add_argument(
        "--between",
        metavar="SYMA,SYMB",
        help=(
            "score the bytes between the end of SYMA and the start of SYMB, "
            "instead of --function/--symbol. " + _between_help_suffix()
        ),
    )
    parser.add_argument(
        "--target-object",
        metavar="FILE",
        help="reference object providing target bytes via --function/--between",
    )
    parser.add_argument(
        "--rom",
        metavar="FILE",
        help="local ROM/binary file providing raw big-endian target bytes",
    )
    parser.add_argument(
        "--rom-offset",
        metavar="0xNNN",
        help="byte offset into --rom; required together with --rom",
    )
    parser.add_argument(
        "--size",
        type=int,
        metavar="BYTES",
        help=(
            "target window size in bytes; only valid with --rom "
            "(default: the candidate function's own size)"
        ),
    )
    parser.add_argument(
        "--control",
        action="append",
        default=[],
        metavar="NAME[@0xOFFSET[:SIZE]]",
        help=(
            "repeatable known-good control function. With --rom, use "
            "NAME@0xOFFSET[:SIZE]; with --target-object, use the bare symbol "
            "NAME. Any control with a nonzero non-relocation diff marks the "
            "run CONTROLS BROKEN."
        ),
    )
    parser.add_argument(
        "--objdump", help="GNU-compatible MIPS objdump; auto-detected when omitted"
    )
    parser.add_argument(
        "--section", default=".text", help="object section (default: .text)"
    )
    parser.add_argument("--json", action="store_true", help="emit JSON")
    parser.set_defaults(handler=score_command)


def _between_help_suffix() -> str:
    return (
        "IDO strips local (static) function symbols, so --function cannot "
        "find them; --between finds the bytes between two symbols IDO did "
        "keep."
    )
