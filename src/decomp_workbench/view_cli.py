"""Terminal rendering and command registration for the aligned mechanism view.

Rendering rules, in the order they matter:

* the verdict chooses emphasis and guidance, never visibility.  Every
  non-matching aligned row is printed, grouped by class.  A verdict that hides
  a difference is a defect by definition;
* the human labels are the JSON keys.  One vocabulary, two renderings;
* glyphs stay ASCII so the screen survives a Windows code page.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from .model import Instruction, display_path
from .objdump import dump_object, parse_disassembly
from .view import (
    DEFAULT_REGISTER_PROFILE,
    MATCH,
    REGISTER_CLASS_PROFILES,
    AlignedRow,
    Hunk,
    MechanismView,
    build_view,
)

ASSEMBLY_WIDTH = 34
WEB_COLORS = ("36", "33", "35", "32", "34", "31")


class Painter:
    """Minimal ANSI painter with a monochrome-safe default."""

    def __init__(self, enabled: bool) -> None:
        self.enabled = enabled

    def _wrap(self, code: str, text: str) -> str:
        return f"\033[{code}m{text}\033[0m" if self.enabled and text else text

    def bold(self, text: str) -> str:
        return self._wrap("1", text)

    def warn(self, text: str) -> str:
        return self._wrap("1;31", text)

    def web(self, number: int, text: str) -> str:
        return self._wrap(WEB_COLORS[(number - 1) % len(WEB_COLORS)], text)


def resolve_color(choice: str, *, stream: Any = None) -> bool:
    """Decide whether ANSI output is appropriate."""

    if choice == "always":
        return True
    if choice == "never":
        return False
    if os.environ.get("NO_COLOR"):
        return False
    target = sys.stdout if stream is None else stream
    return bool(getattr(target, "isatty", lambda: False)())


def _tokens(pairs: Sequence[tuple[str, object]]) -> str:
    return " ".join(f"{key}={value}" for key, value in pairs)


def _range(value: tuple[int, int] | None) -> str:
    return "none" if value is None else f"{value[0]}..{value[1]}"


def _byte_range(value: tuple[int, int] | None) -> str:
    return "none" if value is None else f"0x{value[0]:x}..0x{value[1]:x}"


def _cell(text: str | None, width: int) -> str:
    value = "-" if text is None else text
    if len(value) > width:
        value = value[: width - 1] + "~"
    return value.ljust(width)


def render_header(view: MechanismView) -> list[str]:
    counts = view.counts
    lines: list[str] = []
    title = f"view {view.symbol or 'all-instructions'}"
    lines.append(
        f"{title}  "
        + _tokens(
            (
                ("target_instructions", view.target_instructions),
                ("candidate_instructions", view.candidate_instructions),
                ("aligned_rows", view.aligned_rows),
                ("match", counts.get(MATCH, 0)),
                ("target_frame_size", view.target_frame_size),
                ("candidate_frame_size", view.candidate_frame_size),
            )
        )
    )
    verdict_tokens: list[tuple[str, object]] = [
        ("structural", counts.get("structural", 0)),
        ("schedule", counts.get("schedule", 0)),
        ("register", counts.get("register", 0)),
        ("constant", counts.get("constant", 0)),
    ]
    for optional in ("commutative", "relocation"):
        if counts.get(optional):
            verdict_tokens.append((optional, counts[optional]))
    verdict_tokens.append(("hunks", len(view.hunks)))
    verdict_tokens.append(("playbook", view.playbook))
    lines.append(f"verdict: {view.verdict}  " + _tokens(verdict_tokens))
    lines.append("signature: " + " ".join(view.signature))
    return lines


def render_lanes(view: MechanismView, *, window: int) -> list[str]:
    if not view.lanes:
        return []
    lines = [
        "",
        "REGISTER LANES (per-class assignment sequences, matching instructions "
        "included)",
    ]
    label_width = max(len(lane.classification) for lane in view.lanes)
    for lane in view.lanes:
        total = max(len(lane.target), len(lane.candidate))
        if lane.divergence is not None and total > window:
            start = max(0, lane.divergence - window // 2)
        else:
            start = 0
        end = min(total, start + window)
        widths = []
        for slot in range(start, end):
            left = lane.target[slot] if slot < len(lane.target) else "-"
            right = lane.candidate[slot] if slot < len(lane.candidate) else "-"
            widths.append(max(len(left), len(right)))
        prefix = " " * (2 + label_width + 2)
        target_cells = " ".join(
            (lane.target[slot] if slot < len(lane.target) else "-").ljust(
                widths[slot - start]
            )
            for slot in range(start, end)
        )
        candidate_cells = " ".join(
            (lane.candidate[slot] if slot < len(lane.candidate) else "-").ljust(
                widths[slot - start]
            )
            for slot in range(start, end)
        )
        slots = _tokens((("slots", f"{start}..{max(start, end - 1)}/{total}"),))
        lines.append(
            f"  {lane.classification.ljust(label_width)}  target     "
            f"{target_cells.rstrip()}   {slots}"
        )
        lines.append(f"{prefix}candidate  {candidate_cells.rstrip()}")
        marker_indent = prefix + " " * len("candidate  ")
        if lane.divergence is None:
            lines.append(f"{marker_indent}identical {len(lane.target)}/{total}")
            continue
        offset = sum(widths[: max(0, lane.divergence - start)]) + max(
            0, lane.divergence - start
        )
        detail: list[tuple[str, object]] = [
            ("divergence", lane.divergence),
            ("index", lane.divergence_row),
        ]
        if lane.rotation:
            detail.append(("rotation", f"+{lane.rotation}"))
        lines.append(f"{marker_indent}{'-' * offset}^ " + _tokens(detail))
    return lines


def _annotation(
    row: AlignedRow, webs: dict[tuple[str, str], int], painter: Painter
) -> str:
    parts = []
    for pair in row.substitutions:
        number = webs.get(pair)
        label = f"{pair[0]}->{pair[1]}"
        if number is not None:
            label = painter.web(number, f"{label} [w{number}]")
        parts.append(label)
    return " ".join(parts)


def _assembly_width(view: MechanismView) -> int:
    widest = max(
        (
            len(text)
            for row in view.rows
            for text in (row.target, row.candidate)
            if text is not None
        ),
        default=1,
    )
    return min(widest, ASSEMBLY_WIDTH)


def render_hunks(
    view: MechanismView,
    *,
    context: int,
    max_hunks: int,
    painter: Painter,
) -> list[str]:
    if not view.hunks:
        return []
    webs = {
        (web.target, web.candidate): index for index, web in enumerate(view.webs, 1)
    }
    width = _assembly_width(view)
    lines: list[str] = []
    shown = view.hunks[:max_hunks] if max_hunks else view.hunks
    for hunk in shown:
        lines.append("")
        lines.append(
            painter.bold(f"HUNK {hunk.hunk}")
            + "  "
            + _tokens(
                (
                    ("class", hunk.classification),
                    ("rows", _range((hunk.start, hunk.end))),
                    ("target", _range(hunk.target_range)),
                    ("candidate", _range(hunk.candidate_range)),
                    ("target_bytes", _byte_range(hunk.target_bytes)),
                    ("candidate_bytes", _byte_range(hunk.candidate_bytes)),
                )
            )
        )
        lines.extend(
            _render_hunk_rows(
                view, hunk, context=context, webs=webs, painter=painter, width=width
            )
        )
    if max_hunks and len(view.hunks) > max_hunks:
        lines.append("")
        lines.append(
            f"({len(view.hunks) - max_hunks} further hunk(s) not shown; raise "
            "--max-hunks or use --json)"
        )
    return lines


def _render_hunk_rows(
    view: MechanismView,
    hunk: Hunk,
    *,
    context: int,
    webs: dict[tuple[str, str], int],
    painter: Painter,
    width: int,
) -> list[str]:
    lines: list[str] = []
    start = max(0, hunk.start - context)
    end = min(len(view.rows) - 1, hunk.end + context)
    for row in view.rows[start : end + 1]:
        inside = hunk.start <= row.index <= hunk.end
        marker = ">" if inside else " "
        annotation = _annotation(row, webs, painter) if inside else ""
        if inside and not annotation and not row.matched:
            annotation = row.classification
        lines.append(
            f"  {row.index:5d} {marker} "
            f"{_cell(row.target, width)} | "
            f"{_cell(row.candidate, width)}" + (f"  {annotation}" if annotation else "")
        )
    return lines


def render_webs(view: MechanismView, *, painter: Painter) -> list[str]:
    if not view.webs:
        return []
    lines = ["", "WEBS (one consistent substitution may explain many sites)"]
    for number, web in enumerate(view.webs, 1):
        rows = ",".join(str(item) for item in web.rows[:12])
        if len(web.rows) > 12:
            rows += ",..."
        lines.append(
            "  "
            + painter.web(number, f"{web.web}  {web.target}->{web.candidate}")
            + "  "
            + _tokens((("count", web.count), ("rows", rows)))
        )
    return lines


def render_register_report(view: MechanismView) -> list[str]:
    lines = ["", "REGISTER REPORT (per aligned index, matching rows included)"]
    lines.append(f"  {'index':>5}  {'class':<12}  {'target':<24}  candidate")
    for item in view.register_report():
        target = ",".join(item["target"]) or "-"
        candidate = ",".join(item["candidate"]) or "-"
        lines.append(
            f"  {item['index']:>5}  {item['class']:<12}  {target:<24}  {candidate}"
        )
    return lines


def render_view(
    view: MechanismView,
    *,
    context: int = 2,
    max_hunks: int = 20,
    lane_window: int = 32,
    report_regs: bool = False,
    painter: Painter | None = None,
) -> list[str]:
    """Render the whole screen as lines of monochrome-safe text."""

    brush = painter or Painter(False)
    lines = render_header(view)
    if view.upstream_byte_invisible:
        lines.append(
            brush.warn(
                "state diverges at the first byte difference and the class is "
                "register: the lever is UPSTREAM of hunk 1, not inside it."
            )
        )
    lines.extend(render_lanes(view, window=lane_window))
    lines.extend(
        render_hunks(view, context=context, max_hunks=max_hunks, painter=brush)
    )
    lines.extend(render_webs(view, painter=brush))
    if report_regs:
        lines.extend(render_register_report(view))
    lines.append("")
    for position, entry in enumerate(view.guidance):
        prefix = "next: " if position == 0 else "      "
        lines.append(prefix + entry)
    return [line.rstrip() for line in lines]


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------


def _emit(view: MechanismView, args: argparse.Namespace) -> int:
    if args.json:
        print(
            json.dumps(
                view.as_dict(report_regs=args.report_regs), indent=2, sort_keys=True
            )
        )
    else:
        painter = Painter(resolve_color(args.color))
        for line in render_view(
            view,
            context=args.context,
            max_hunks=args.max_hunks,
            lane_window=args.lane_window,
            report_regs=args.report_regs,
            painter=painter,
        ):
            print(line)
    if args.fail_on_mismatch and view.verdict not in {"exact", "words-identical"}:
        return 1
    return 0


def _symbol(args: argparse.Namespace) -> str | None:
    value = getattr(args, "symbol", None) or getattr(args, "function", None)
    return str(value) if value else None


def view_command(args: argparse.Namespace) -> int:
    """Render the aligned mechanism view for two object files."""

    symbol = _symbol(args)
    try:
        _, target = dump_object(
            args.target, objdump=args.objdump, symbol=symbol, section=args.section
        )
        _, candidate = dump_object(
            args.candidate, objdump=args.objdump, symbol=symbol, section=args.section
        )
        view = build_view(
            target,
            candidate,
            target_name=display_path(args.target),
            candidate_name=display_path(args.candidate),
            symbol=symbol,
            register_profile=args.register_profile,
        )
    except (OSError, RuntimeError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    return _emit(view, args)


def view_dumps_command(args: argparse.Namespace) -> int:
    """Render the aligned mechanism view from retained GNU objdump text."""

    symbol = _symbol(args)
    try:
        target_text = Path(args.target).read_text(encoding="utf-8")
        candidate_text = Path(args.candidate).read_text(encoding="utf-8")
    except OSError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    target: list[Instruction] = parse_disassembly(target_text, symbol=symbol)
    candidate: list[Instruction] = parse_disassembly(candidate_text, symbol=symbol)
    if not target or not candidate:
        detail = f" for symbol {symbol!r}" if symbol else ""
        print(
            "error: both files must contain GNU-style objdump instruction "
            f"lines{detail}",
            file=sys.stderr,
        )
        return 2
    try:
        view = build_view(
            target,
            candidate,
            target_name=display_path(args.target),
            candidate_name=display_path(args.candidate),
            symbol=symbol,
            register_profile=args.register_profile,
        )
    except ValueError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    return _emit(view, args)


def _add_shared_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--symbol",
        "--function",
        dest="symbol",
        help="view only this exact function (decomp and GNU vocabulary agree here)",
    )
    parser.add_argument("--json", action="store_true", help="emit JSON")
    parser.add_argument(
        "--report-regs",
        action="store_true",
        help="report per-aligned-index register operands, matching rows included",
    )
    parser.add_argument(
        "--context",
        type=int,
        default=2,
        help="aligned rows of context around each hunk (default: 2)",
    )
    parser.add_argument(
        "--max-hunks",
        type=int,
        default=20,
        help="maximum hunks to render; 0 renders all (default: 20)",
    )
    parser.add_argument(
        "--lane-window",
        type=int,
        default=32,
        help="lane slots to render around a divergence (default: 32)",
    )
    parser.add_argument(
        "--register-profile",
        default=DEFAULT_REGISTER_PROFILE,
        choices=sorted(REGISTER_CLASS_PROFILES),
        help=(
            f"register class table for the lanes (default: {DEFAULT_REGISTER_PROFILE})"
        ),
    )
    parser.add_argument(
        "--color",
        choices=("auto", "always", "never"),
        default="auto",
        help="ANSI web coloring; monochrome annotations are always present",
    )
    parser.add_argument(
        "--fail-on-mismatch",
        action="store_true",
        help="return exit 1 unless the verdict is exact or words-identical",
    )


def register_view_commands(commands: argparse._SubParsersAction[Any]) -> None:
    """Register ``view`` and ``view-dumps`` on an existing subparser set."""

    view_parser = commands.add_parser(
        "view",
        help="aligned mechanism view of a target and candidate object",
        description=(
            "LCS-aligned diagnosis: taxonomy verdict, classified hunks, "
            "per-class register lanes, prefix signature, and the lever family "
            "for the dominant class."
        ),
    )
    view_parser.add_argument("target", help="reference object")
    view_parser.add_argument("candidate", help="candidate object")
    view_parser.add_argument(
        "--section", default=".text", help="object section (default: .text)"
    )
    view_parser.add_argument(
        "--objdump",
        help="GNU-compatible MIPS objdump; auto-detected when omitted",
    )
    _add_shared_arguments(view_parser)
    view_parser.set_defaults(handler=view_command)

    dumps_parser = commands.add_parser(
        "view-dumps",
        help="aligned mechanism view from retained GNU objdump text",
        description=(
            "Run the aligned mechanism view on redistributable objdump text, "
            "so every visualization works without object files."
        ),
    )
    dumps_parser.add_argument("target", help="reference objdump text")
    dumps_parser.add_argument("candidate", help="candidate objdump text")
    _add_shared_arguments(dumps_parser)
    dumps_parser.set_defaults(handler=view_dumps_command)
