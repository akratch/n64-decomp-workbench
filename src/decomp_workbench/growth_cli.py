"""Command journey for split growth: `trace growth`.

Three questions over one CDX log from the globalcolor profile: which blocks a
decided web spans and how its split piece grew (`--web`), whether every
recorded growth verdict in the procedure follows the rule (`--census`), and
which interferers a web saw at each decision (`--neighbours`).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from .globalcolor import parse_globalcolor_trace
from .growth import (
    GrowthError,
    growth_report,
    index_growth,
    neighbour_report,
    rule_census,
)
from .terminal import add_terminal_arguments, emit_lines

__all__ = ["register_growth_command"]


def _blocks_argument(value: str) -> list[int]:
    try:
        return [int(item, 0) for item in value.split(",") if item.strip()]
    except ValueError:
        raise argparse.ArgumentTypeError(
            f"{value!r} is not a comma-separated block list"
        ) from None


def _growth_lines(report: dict[str, Any]) -> list[str]:
    blocks = report["blocks"]
    lines = [
        f"web {report['web']}  lr={blocks['live_range']}  "
        f"decisions={blocks['decisions']}  "
        f"{'split piece' if report['split'] else 'not split'}",
        f"  span        {' '.join(map(str, blocks['span'])) or '-'}",
        f"  passthrough {' '.join(map(str, blocks['passthrough'])) or '-'}",
        f"  references  {' '.join(map(str, blocks['references'])) or '-'}",
    ]
    if report["seed"] is not None:
        lines.append(f"  seed bb={report['seed']}")
    if report["tests"]:
        lines.append(f"  growth ({report['rule']})")
    for test in report["tests"]:
        verdict = {True: "ACCEPT", False: "reject", None: "no verdict"}[
            test["accepted"]
        ]
        note = "" if test["agrees"] is not False else "  DISAGREES WITH THE RULE"
        lines.append(
            f"    bb={test['block']:>5} new={test['new']} left "
            f"{test['left_before']}->{test['left_after']} "
            f"numintf={test['numintf']} headroom={test['headroom']:+d} "
            f"margin={test['margin']:+d}  {verdict}{note}"
        )
    for move in report["liveblock_moves"]:
        lines.append(f"    livbb {move['op']} bb={move['block']} refs={move['refs']}")
    nearest = report["nearest_rejection"]
    if nearest is not None:
        lines.append(
            f"  nearest rejection: bb={nearest['block']} short by "
            f"{nearest['shortfall']} -- read its interferers with --neighbours "
            f"--window {nearest['block']} on a CDX_DETAIL_WEB={report['web']} "
            "capture"
        )
    if report["disagreements"]:
        lines.append(
            "  the rule does not explain block(s) "
            + ", ".join(map(str, report["disagreements"]))
            + "; the instrument or the rule is wrong here, and the record wins"
        )
    return lines


def _census_lines(report: dict[str, Any]) -> list[str]:
    lines = [
        f"growth census: {report['tests']} test(s) over {report['pieces']} "
        f"piece(s); {report['agree']} of {report['judged']} judged agree with "
        "the rule",
        f"  rule: {report['rule']}",
        "  margin histogram: "
        + " ".join(
            f"{key}:{value}" for key, value in report["margin_histogram"].items()
        ),
    ]
    for test in report["disagree"]:
        lines.append(
            f"  DISAGREES bb={test['block']} new={test['new']} left "
            f"{test['left_before']}->{test['left_after']} numintf={test['numintf']} "
            f"accepted={test['accepted']}"
        )
    if report["unjudged"]:
        lines.append(f"  {report['unjudged']} test(s) had no growv verdict row")
    return lines


def _neighbour_lines(report: dict[str, Any]) -> list[str]:
    window = report["window"]
    lines = [
        f"neighbours of {report['phase']} web {report['web']}"
        + (f" live in blocks {','.join(map(str, window))}" if window else "")
    ]
    for decision in report["decisions"]:
        lines.append(
            f"  decision {decision['index']}: {decision['decision']} "
            f"save={decision['save']} numintf={decision['numintf']} "
            f"regsleft={decision['regsleft']} -> "
            f"{len(decision['neighbours'])} neighbour(s)"
        )
        for entry in decision["neighbours"]:
            shown = entry.get("in_window") or entry.get("blocks", [])[:12]
            lines.append(
                f"    w{entry['web']:<6} sym={entry.get('sym', '?')!s:<6} "
                f"{entry.get('register') or '-':<5} "
                f"{' '.join(map(str, shown))}"
            )
        if decision["index"]:
            lines.append(
                f"    gone: {decision['gone'] or '-'}  new: {decision['new'] or '-'}"
            )
    return lines


def growth_command(args: argparse.Namespace) -> int:
    try:
        text = Path(args.log).read_text(encoding="utf-8", errors="replace")
        trace = parse_globalcolor_trace(text)
        if args.neighbours:
            if args.web is None:
                raise GrowthError("--neighbours needs --web")
            report = neighbour_report(
                trace, web=args.web, proc=args.proc, window=args.window or ()
            )
            lines = _neighbour_lines(report)
        elif args.census:
            report = rule_census(index_growth(trace, proc=args.proc))
            lines = _census_lines(report)
        else:
            if args.web is None:
                raise GrowthError("name a web with --web, or pass --census")
            report = growth_report(index_growth(trace, proc=args.proc), args.web)
            lines = _growth_lines(report)
    except (GrowthError, OSError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0
    emit_lines(lines, width=args.width, pager=args.pager)
    if args.census and report["disagree"]:
        return 1
    return 0


def register_growth_command(commands: argparse._SubParsersAction[Any]) -> None:
    """Register ``trace-growth`` behind the ``trace growth`` spelling."""

    parser = commands.add_parser(
        "trace-growth",
        help="a web's block sets and split growth, with each test's margins",
        description=(
            "Read the globalcolor profile's per-web block sets and split-growth "
            "rows. With --web: the decided piece's span, passthrough and "
            "reference blocks, its seed, and every growth test with both "
            "margins and its verdict. With --census: every recorded test in "
            "the procedure checked against the rule. With --neighbours --web: "
            "the interferers at each of the web's decisions (needs a "
            "CDX_DETAIL_WEB=<web> capture), optionally only those live in "
            "--window blocks, and what changed between decisions."
        ),
        epilog=(
            "example: decomp-workbench trace growth "
            "examples/traces/split-growth.log --web 202"
        ),
    )
    parser.add_argument("log", help="CDX log from the instrumented uopt")
    parser.add_argument("--web", type=int, metavar="N", help="the web to read")
    parser.add_argument("--proc", type=int, metavar="N", help="procedure ordinal")
    parser.add_argument(
        "--census",
        action="store_true",
        help="check every recorded growth verdict against the rule; exit 1 on "
        "a disagreement",
    )
    parser.add_argument(
        "--neighbours",
        "--neighbors",
        dest="neighbours",
        action="store_true",
        help="list the web's interferers at each decision",
    )
    parser.add_argument(
        "--window",
        type=_blocks_argument,
        metavar="BB[,BB...]",
        help="with --neighbours, keep only interferers live in these blocks",
    )
    parser.add_argument("--json", action="store_true", help="emit JSON")
    add_terminal_arguments(parser)
    parser.set_defaults(handler=growth_command, report_command="trace-growth")
