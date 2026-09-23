"""Command journey for the colour landscape: `sweep landscape`.

One command, two modes. Given a source it captures the held baseline's trace,
plans every probe from it, compiles the cells through the campaign engine and
writes a `decomp-workbench-landscape-v1` report into its state directory. Given
`--report` it re-reads a saved landscape without compiling, repacks it, and
refuses a landscape whose source has moved since it was measured.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

from .cli_options import add_symbol_argument
from .environment import merge_toolchain_environment, parse_environment
from .landscape import (
    DEFAULT_WINDOW,
    LandscapeRun,
    freshness,
    repack,
    run_landscape,
    state_directory,
    write_report,
)

__all__ = ["register_landscape_command", "render_landscape"]


def _window(value: str) -> int:
    try:
        width = int(value, 0)
    except ValueError:
        raise argparse.ArgumentTypeError(f"{value!r} is not an integer") from None
    if width <= 0 or width % 4:
        raise argparse.ArgumentTypeError("--window must be a positive multiple of 4")
    return width


def render_landscape(report: dict[str, Any], *, limit: int = 20) -> list[str]:
    """The terminal form of one landscape document."""

    hold = report.get("hold") or []
    base = report.get("base_score")
    lines = [
        f"colour landscape ({report.get('order')} order): "
        f"{report.get('measured_probes')} measured of "
        f"{report.get('planned_probes')} planned probe(s), proc "
        f"{report.get('procedure')}, windows of {int(report.get('window') or 0):#x} "
        "bytes"
    ]
    if hold:
        lines.append(
            "held in every cell (scores, footprints and the packing are "
            "relative to this set; a winner is a force to ADD to it):"
        )
        lines.extend(f"  {force}" for force in hold)
    lines.append(
        f"baseline: {base} masked word(s)"
        + (
            f", trace identity {report['trace_identity']}"
            if report.get("trace_identity")
            else ""
        )
    )
    found = report.get("winners") or []
    lines.append(
        f"winners beating the {'held' if hold else 'unforced'} baseline at "
        f"delta 0: {len(found)}"
    )
    for row in found[:limit]:
        lines.append(f"  {row['force']:<16} {row['score']:>6}  ({-row['gain']:+d})")
    if len(found) > limit:
        lines.append(f"  ... {len(found) - limit} more; use --json")
    for group in report.get("rivals") or []:
        lines.append(
            f"RIVALS -- one question, {len(group)} handles, identical radius: "
            + " ".join(group)
        )
    packing = report.get("packing") or {}
    if packing.get("forces"):
        lines.append(
            f"best disjoint set, one colour per web -> predicted "
            f"{packing['predicted_score']}:"
        )
        for member in packing["members"]:
            lines.append(
                f"  {member['force']:<16} ({-member['gain']:+d})  radius "
                + " ".join(member["radius"])
            )
        if packing.get("truncated"):
            lines.append(
                f"  (packed over the best {packing['winners_considered']} winners only)"
            )
        lines.append(
            "measure it before holding it: the prediction assumes additivity, "
            "which disjoint radii imply but do not guarantee"
        )
        next_hold = report.get("next_hold") or []
        lines.append(
            "next order: sweep landscape ... "
            + " ".join(f"--hold {force}" for force in next_hold)
        )
    if report.get("closure"):
        lines.append(f"closure: {report['closure']}")
    moved = report.get("moved_nothing") or []
    if moved:
        lines.append(f"moved nothing (colour is free there): {len(moved)} probe(s)")
    size = report.get("size_changed") or []
    if size:
        lines.append(f"changed the size (excluded): {' '.join(size[:limit])}")
    for row in report.get("not_probed") or []:
        lines.append(f"not probed: w{row['web']} {row.get('reason') or ''}".rstrip())
    nomination = report.get("nomination") or []
    if nomination:
        lines.append("window -> forces that move it, strongest first:")
        for entry in nomination[:limit]:
            lines.append(f"  {entry['window']:>8}  " + " ".join(entry["forces"][:8]))
    for warning in report.get("warnings") or []:
        lines.append(f"warning: {warning}")
    lines.append(f"proof: {report.get('proof')}")
    return lines


def _report_mode(args: argparse.Namespace) -> int:
    path = Path(args.report).expanduser()
    try:
        saved = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(saved, dict) or saved.get("schema") != (
            "decomp-workbench-landscape-v1"
        ):
            raise ValueError(f"not a decomp-workbench landscape report: {path}")
        report = repack(saved)
    except (OSError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    source = Path(args.source).expanduser() if args.source else None
    warning = freshness(report, source=source)
    report["freshness"] = warning
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        if warning:
            print(f"!! {warning}")
        print("\n".join(render_landscape(report, limit=args.limit)))
    return 1 if warning and warning.startswith("STALE") else 0


def landscape_command(args: argparse.Namespace) -> int:
    if args.report:
        return _report_mode(args)
    missing = [
        name
        for name, value in (
            ("SOURCE", args.source),
            ("--target", args.target),
            ("--toolchain", args.toolchain),
            ("--compile-command", args.compile_command),
        )
        if not value
    ]
    if missing:
        print(
            "error: a landscape run needs " + ", ".join(missing) + "; or pass "
            "--report FILE to re-read a saved landscape",
            file=sys.stderr,
        )
        return 2
    try:
        environment = merge_toolchain_environment(
            parse_environment(args.env), args.toolchain, require_ready=True
        )
        source = Path(args.source).expanduser().resolve()
        state = state_directory(
            Path(args.state_dir).expanduser().resolve(),
            source=source,
            hold=tuple(args.hold),
            proc=args.proc,
        )
        report = run_landscape(
            LandscapeRun(
                source=source,
                target=Path(args.target).expanduser().resolve(),
                template=args.compile_command,
                environment=environment,
                cache_dir=Path(args.cache_dir).expanduser().resolve(),
                state_dir=state,
                proc=args.proc,
                hold=tuple(args.hold),
                trace=Path(args.trace).expanduser().resolve() if args.trace else None,
                every_colour=args.every_colour,
                cross_kind=args.cross_kind,
                webs=tuple(args.web),
                limit=args.probe_limit,
                window=args.window,
                jobs=args.jobs,
                objdump=args.objdump,
                symbol=args.symbol,
                section=args.section,
                compile_cwd=(
                    Path(args.compile_cwd).expanduser().resolve()
                    if args.compile_cwd
                    else Path.cwd().resolve()
                ),
                timeout=args.timeout,
            )
        )
        report["state"] = {
            "directory": str(state),
            "report": str(state / "report.json"),
        }
        write_report(state / "report.json", report)
    except (OSError, RuntimeError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print("\n".join(render_landscape(report, limit=args.limit)))
        print(f"report: {state / 'report.json'}")
    return 0 if report["measured_probes"] else 1


def register_landscape_command(commands: argparse._SubParsersAction[Any]) -> None:
    """Register the flat `sweep-landscape` behind the `sweep landscape` spelling."""

    parser = commands.add_parser(
        "sweep-landscape",
        help=argparse.SUPPRESS,
        description=(
            "Probe every coloured phase-one web against a baseline compiled "
            "with a held force set, map each probe's footprint by window, and "
            "pack the winners by their radii. With no --hold this is the "
            "first-order landscape; holding a measured packing gives the "
            "second order, and holding that packing's result the third. The "
            "probe plan is read from the held baseline's own trace, so --trace "
            "is refused alongside --hold. Forced objects are never source "
            "matches."
        ),
        epilog=(
            "example: decomp-workbench sweep landscape --report "
            "examples/fixtures/landscape-report.json"
        ),
    )
    parser.add_argument("source", nargs="?", help="the C source to compile")
    parser.add_argument("--target", help="the target object")
    parser.add_argument("--toolchain", help="an instrumented, gated toolchain")
    parser.add_argument(
        "--compile-command",
        help="compiler template with {source} and {output}",
    )
    parser.add_argument(
        "--hold",
        action="append",
        default=[],
        metavar="p1:wN=cM",
        help=(
            "a force kept applied in the baseline and in every probe; "
            "repeatable, or comma-separated"
        ),
    )
    parser.add_argument(
        "--trace",
        help=(
            "an unforced CDX trace to plan from instead of capturing one; "
            "refused with --hold"
        ),
    )
    parser.add_argument(
        "--proc", type=int, default=0, help="globalcolor procedure ordinal"
    )
    parser.add_argument(
        "--every-colour",
        "--every-color",
        dest="every_colour",
        action="store_true",
        help="probe every legal same-kind colour of each web, not one",
    )
    parser.add_argument(
        "--cross-kind",
        action="store_true",
        help="also probe colours of the other save kind (these usually move size)",
    )
    parser.add_argument(
        "--web",
        type=int,
        action="append",
        default=[],
        metavar="N",
        help="probe only this web; repeatable",
    )
    parser.add_argument(
        "--probe-limit",
        type=int,
        default=0,
        metavar="N",
        help="compile at most N probes (0: all)",
    )
    parser.add_argument(
        "--window",
        type=_window,
        default=DEFAULT_WINDOW,
        metavar="BYTES",
        help=f"footprint window width (default {DEFAULT_WINDOW:#x})",
    )
    parser.add_argument(
        "--report",
        metavar="FILE",
        help=(
            "re-read a saved landscape report without compiling: repack it, "
            "and exit 1 when SOURCE (or the recorded source) has changed"
        ),
    )
    add_symbol_argument(parser)
    parser.add_argument("--section", default=".text")
    parser.add_argument("--objdump")
    parser.add_argument("--env", action="append", default=[], metavar="NAME=VALUE")
    parser.add_argument("--compile-cwd")
    parser.add_argument("--jobs", type=int, default=max(1, min(8, os.cpu_count() or 1)))
    parser.add_argument("--timeout", type=float, default=120.0)
    parser.add_argument("--cache-dir", default=".decomp-workbench/cache")
    parser.add_argument("--state-dir", default=".decomp-workbench")
    parser.add_argument(
        "--limit", type=int, default=20, help="terminal rows per section"
    )
    parser.add_argument("--json", action="store_true", help="emit JSON")
    parser.set_defaults(handler=landscape_command, report_command="sweep-landscape")
