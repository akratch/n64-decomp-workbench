"""Combined exact comparison and aligned mechanism diagnosis commands."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from .census import (
    Predicate,
    census_status,
    evaluate_census,
    parse_census,
)
from .cli_options import (
    add_census_argument,
    add_explain_keys_argument,
    add_symbol_argument,
)
from .comparison_render import (
    comparison_acceptance,
    comparison_explanation_lines,
    comparison_line,
    diff_site_lines,
)
from .diagnosis import Diagnosis, diagnose_dumps, diagnose_objects
from .force_spec import write_force_specification
from .html_report import render_diagnosis_html
from .schema import COMPARISON_CENSUS_KEYS
from .terminal import emit_lines
from .view_cli import (
    Painter,
    add_view_output_arguments,
    add_view_render_arguments,
    render_view,
    resolve_color,
)


def _emit(
    diagnosis: Diagnosis,
    args: argparse.Namespace,
    predicates: Sequence[Predicate],
) -> int:
    comparison = diagnosis.comparison
    if args.json and args.html:
        print("error: --json and --html are mutually exclusive", file=sys.stderr)
        return 2
    try:
        census = evaluate_census(predicates, comparison.as_dict())
    except ValueError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    try:
        force_output = (
            Path(args.emit_force_spec).expanduser().resolve()
            if args.emit_force_spec
            else None
        )
        html_output = Path(args.html).expanduser().resolve() if args.html else None
        for output, label in (
            (force_output, "force specification"),
            (html_output, "HTML report"),
        ):
            if output is not None and output.exists():
                raise FileExistsError(f"refusing to overwrite {label}: {output}")
        if force_output is not None:
            write_force_specification(diagnosis.view, force_output)
        if html_output is not None:
            html_output.parent.mkdir(parents=True, exist_ok=True)
            document = render_diagnosis_html(
                diagnosis.view,
                comparison=comparison,
                report_regs=args.report_regs,
            )
            with html_output.open("x", encoding="utf-8") as destination:
                destination.write(document)
    except (OSError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2

    accepted, _ = comparison_acceptance(comparison, cross_rom=args.cross_rom)
    if args.json:
        payload = diagnosis.as_dict(
            report_regs=args.report_regs,
            cross_rom=args.cross_rom,
        )
        if census:
            nested = payload["comparison"]
            if isinstance(nested, dict):
                nested["census"] = [item.as_dict() for item in census]
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        lines = ["COMPARISON", comparison_line(comparison)]
        for line in comparison_explanation_lines(
            comparison,
            cross_rom=args.cross_rom,
        ):
            if not line.startswith("next: "):
                lines.append(line)
        if args.show_diff or args.show_all:
            lines.extend(diff_site_lines(comparison))
        lines.extend(("", "MECHANISM"))
        painter = Painter(resolve_color(args.color))
        lines.extend(
            render_view(
                diagnosis.view,
                context=args.context,
                max_hunks=0 if args.show_all else args.max_hunks,
                lane_window=(
                    max(
                        diagnosis.view.target_instructions,
                        diagnosis.view.candidate_instructions,
                    )
                    if args.show_all
                    else args.lane_window
                ),
                report_regs=args.report_regs,
                painter=painter,
            )
        )
        lines.extend(item.line for item in census)
        if args.html:
            lines.append(f"HTML report: {Path(args.html).expanduser().resolve()}")
        if args.emit_force_spec:
            lines.append(
                "diagnostic force specification: "
                f"{Path(args.emit_force_spec).expanduser().resolve()}"
            )
        emit_lines(
            lines,
            width=args.width,
            pager=args.pager,
        )

    return census_status(
        census,
        otherwise=1 if args.fail_on_mismatch and not accepted else 0,
    )


def diagnose_command(args: argparse.Namespace) -> int:
    """Diagnose two object files after disassembling each exactly once."""

    try:
        predicates = parse_census(args.census, allowed=COMPARISON_CENSUS_KEYS)
        diagnosis = diagnose_objects(
            args.target,
            args.candidate,
            objdump=args.objdump,
            symbol=args.symbol,
            section=args.section,
            register_profile=args.register_profile,
        )
    except (OSError, RuntimeError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    return _emit(diagnosis, args, predicates)


def diagnose_dumps_command(args: argparse.Namespace) -> int:
    """Diagnose two retained GNU objdump text files."""

    try:
        predicates = parse_census(args.census, allowed=COMPARISON_CENSUS_KEYS)
        diagnosis = diagnose_dumps(
            args.target,
            args.candidate,
            symbol=args.symbol,
            register_profile=args.register_profile,
        )
    except (OSError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    return _emit(diagnosis, args, predicates)


def _add_shared_arguments(
    parser: argparse.ArgumentParser,
    *,
    object_inputs: bool,
) -> None:
    add_symbol_argument(parser)
    add_explain_keys_argument(parser)
    if object_inputs:
        parser.add_argument(
            "--section",
            default=".text",
            help="object section (default: .text)",
        )
        parser.add_argument(
            "--objdump",
            help="GNU-compatible MIPS objdump; auto-detected when omitted",
        )
    parser.add_argument("--json", action="store_true", help="emit JSON")
    add_view_render_arguments(parser, default_max_hunks=1)
    add_view_output_arguments(parser)
    parser.add_argument(
        "--show-all",
        action="store_true",
        help="render every hunk, full lanes, and literal differing sites",
    )
    parser.add_argument(
        "--show-diff",
        action="store_true",
        help="print every positional differing site as well as the aligned hunk",
    )
    parser.add_argument(
        "--cross-rom",
        action="store_true",
        help=(
            "accept structural cross-ROM evidence; never call it an "
            "object-exact source match"
        ),
    )
    parser.add_argument(
        "--fail-on-mismatch",
        action="store_true",
        help="return exit 1 unless exact, or structurally exact with --cross-rom",
    )
    add_census_argument(parser)


def register_diagnose_commands(commands: argparse._SubParsersAction[Any]) -> None:
    """Register combined diagnosis commands."""

    parser = commands.add_parser(
        "diagnose",
        help="compare and explain two MIPS objects in one screen",
        description=(
            "Disassemble each object once, then render exact comparison truth "
            "and the decisive aligned mechanism evidence."
        ),
    )
    parser.add_argument("target", help="reference object")
    parser.add_argument("candidate", help="candidate object")
    _add_shared_arguments(parser, object_inputs=True)
    parser.set_defaults(handler=diagnose_command)

    dumps = commands.add_parser(
        "diagnose-dumps",
        help="compare and explain retained GNU objdump text",
        description=(
            "Build the combined exact and aligned diagnosis from redistributable "
            "objdump text."
        ),
    )
    dumps.add_argument("target", help="reference objdump text")
    dumps.add_argument("candidate", help="candidate objdump text")
    _add_shared_arguments(dumps, object_inputs=False)
    dumps.set_defaults(handler=diagnose_dumps_command)
