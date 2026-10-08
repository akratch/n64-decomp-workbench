"""Command journey for the per-web allocator report: `trace web-report`."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from .terminal import add_terminal_arguments, emit_lines
from .web_report import (
    WEBREPORT_RECORDS,
    Namer,
    build_web_report,
    choose_procedure,
    parse_records,
    procedures_with_lines,
    render_web_report,
    web_report_payload,
)

__all__ = ["register_web_report_command", "web_report_command"]


def _offset_name(value: str) -> tuple[int, str]:
    offset, separator, name = value.partition("=")
    try:
        number = int(offset, 0)
    except ValueError:
        number = None
    if not separator or number is None or not name.isidentifier():
        raise argparse.ArgumentTypeError(
            f"{value!r} is not OFFSET=NAME (for example -28=col)"
        )
    return number, name


def _span(value: str) -> tuple[int, int]:
    low, _, high = value.partition("-")
    try:
        first = int(low)
        last = int(high or low)
    except ValueError:
        raise argparse.ArgumentTypeError(
            f"{value!r} is not a line span LO-HI"
        ) from None
    if last < first:
        raise argparse.ArgumentTypeError(f"{value!r} ends before it starts")
    return first, last


def web_report_command(args: argparse.Namespace) -> int:
    try:
        text = Path(args.log).read_text(encoding="utf-8", errors="replace")
        source = (
            Path(args.source).read_text(encoding="utf-8", errors="replace").splitlines()
            if args.source
            else []
        )
    except OSError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    records = parse_records(text)
    if not any(kind in WEBREPORT_RECORDS for kind, _ in records):
        print(
            "error: the log carries none of the CDX_WEBREPORT records ("
            + ", ".join(WEBREPORT_RECORDS)
            + "); they come from a campaign-local uopt patch, not the shipped "
            "globalcolor profile. See docs/web-report.md.",
            file=sys.stderr,
        )
        return 2
    proc = args.proc if args.proc is not None else choose_procedure(records, args.lines)
    if proc is None:
        found = sorted(procedures_with_lines(records))
        print(
            "error: cannot tell which procedure to report; pass --proc, or "
            "--lines with the function's definition span. Procedures with "
            f"lines: {found}",
            file=sys.stderr,
        )
        return 2
    report = build_web_report(records, proc)
    if not report.decisions:
        print(f"error: no allocator decisions for procedure {proc}", file=sys.stderr)
        return 2
    locals_by_offset: dict[int, list[str]] = {}
    for offset, name in args.local:
        locals_by_offset.setdefault(offset, []).append(name)
    namer = Namer(locals_by_offset, dict(args.param))
    payload: dict[str, Any] = web_report_payload(
        report,
        namer,
        source=source,
        webs=set(args.web) or None,
        block_filter=args.block,
    )
    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0
    header = f"proc {proc}  {len(report.decisions)} decisions  log {args.log}" + (
        f"  source {args.source}" if args.source else ""
    )
    emit_lines(render_web_report(payload, header), width=args.width, pager=args.pager)
    return 0


def register_web_report_command(commands: argparse._SubParsersAction[Any]) -> None:
    """Register ``web-report`` behind the ``trace web-report`` spelling."""

    parser = commands.add_parser(
        "web-report",
        help="why each web got its colour: references, forbidden seed, splits",
        description=(
            "Per-web allocator report over one CDX log captured with the "
            "campaign-local CDX_WEBREPORT records. For each decision of one "
            "procedure: the web's value as an expression, its save arithmetic "
            "broken down per reference block (checked against totalsave), the "
            "forbidden seed with the precoloured value behind each bit, and for "
            "a split web every growth test re-checked against the L161 rule "
            "with the first refused block named. Reads a log; never compiles."
        ),
        epilog=(
            "example: decomp-workbench trace web-report "
            "examples/traces/web-report.log --local -28=col --param 0=grid"
        ),
    )
    parser.add_argument("log", help="CDX log with CDX_WEBREPORT records")
    parser.add_argument("--proc", type=int, metavar="N", help="procedure ordinal")
    parser.add_argument(
        "--lines",
        type=_span,
        metavar="LO-HI",
        help="choose the procedure whose first line falls in this source span",
    )
    parser.add_argument(
        "--web",
        type=int,
        action="append",
        default=[],
        metavar="N",
        help="only this web",
    )
    parser.add_argument(
        "--block", type=int, metavar="BB", help="only this block's rows"
    )
    parser.add_argument(
        "--source", help="the compiled C source, to name the lines that mention a web"
    )
    parser.add_argument(
        "--local",
        type=_offset_name,
        action="append",
        default=[],
        metavar="OFFSET=NAME",
        help="name a local by its frame offset (repeatable)",
    )
    parser.add_argument(
        "--param",
        type=_offset_name,
        action="append",
        default=[],
        metavar="OFFSET=NAME",
        help="name a parameter by its offset (repeatable)",
    )
    parser.add_argument("--json", action="store_true", help="emit JSON")
    add_terminal_arguments(parser)
    parser.set_defaults(handler=web_report_command, report_command="web-report")
