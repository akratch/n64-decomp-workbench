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
from typing import Any, TextIO

from .census import (
    Predicate,
    census_status,
    evaluate_census,
    parse_census,
    print_census,
)
from .cli_options import (
    add_census_argument,
    add_explain_keys_argument,
    add_symbol_argument,
)
from .model import Instruction, display_path
from .objdump import dump_object, parse_disassembly
from .schema import VIEW_CENSUS_KEYS
from .view import (
    DEFAULT_REGISTER_PROFILE,
    MATCH,
    REGISTER_CLASS_PROFILES,
    AlignedRow,
    Hunk,
    MechanismView,
    build_view,
)

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


def resolve_color(choice: str, *, stream: TextIO | None = None) -> bool:
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
    """Render one assembly column, padded but never truncated."""

    return ("-" if text is None else text).ljust(width)


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
                ("register_profile", view.register_profile),
            )
        )
    )
    verdict_tokens: list[tuple[str, object]] = [
        ("structural", counts.get("structural", 0)),
        ("schedule", counts.get("schedule", 0)),
        ("register", counts.get("register", 0)),
        ("constant", counts.get("constant", 0)),
    ]
    for optional in ("commutative", "relocation", "displacement"):
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


def _assembly_width(rows: Sequence[AlignedRow]) -> int:
    """Return the column width needed to render these rows in full.

    Columns are sized per hunk window and never capped.  A fixed cap truncates,
    and two instructions that differ only near their end then render as the
    same text -- a screen whose whole purpose is to show that difference would
    be hiding it.  A wide row is allowed to be wide.
    """

    return max(
        (
            len(text)
            for row in rows
            for text in (row.target, row.candidate)
            if text is not None
        ),
        default=1,
    )


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
    lines: list[str] = []
    shown = view.hunks[:max_hunks] if max_hunks else view.hunks
    windows = _context_windows(view, shown, context=context)
    for hunk, window in zip(shown, windows, strict=True):
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
            _render_hunk_rows(view, hunk, window=window, webs=webs, painter=painter)
        )
    if max_hunks and len(view.hunks) > max_hunks:
        lines.append("")
        lines.append(
            f"({len(view.hunks) - max_hunks} further hunk(s) not shown; raise "
            "--max-hunks or use --json)"
        )
    return lines


def _context_windows(
    view: MechanismView, hunks: Sequence[Hunk], *, context: int
) -> list[tuple[int, int]]:
    """Return the inclusive row range to print for each hunk.

    Context is clamped to the midpoint between neighbouring hunks so that no
    aligned row is ever printed twice.  A row shown under two hunks reads as
    two separate findings.
    """

    windows: list[tuple[int, int]] = []
    last = len(view.rows) - 1
    for position, hunk in enumerate(hunks):
        low = max(0, hunk.start - context)
        high = min(last, hunk.end + context)
        if position:
            previous = hunks[position - 1]
            low = max(low, (previous.end + hunk.start) // 2 + 1)
        if position + 1 < len(hunks):
            following = hunks[position + 1]
            high = min(high, (hunk.end + following.start) // 2)
        windows.append((low, max(low, high)))
    return windows


def _render_hunk_rows(
    view: MechanismView,
    hunk: Hunk,
    *,
    window: tuple[int, int],
    webs: dict[tuple[str, str], int],
    painter: Painter,
) -> list[str]:
    start, end = window
    rows = view.rows[start : end + 1]
    width = _assembly_width(rows)
    lines: list[str] = []
    for row in rows:
        inside = hunk.start <= row.index <= hunk.end
        marker = ">" if inside else " "
        annotation = _annotation(row, webs, painter) if inside else ""
        if not annotation and not row.matched:
            # Context rows carry their class too: a displacement never opens a
            # hunk, and it must still be visible where it happens.
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
    if view.register_first_divergence:
        lines.append(
            brush.warn(
                "the FIRST divergence is a register-class divergence, not a "
                "structural one: the decision was made upstream of hunk 1 even "
                "though it surfaces there."
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


def _emit(
    view: MechanismView,
    args: argparse.Namespace,
    predicates: Sequence[Predicate] = (),
) -> int:
    payload = view.as_dict(report_regs=args.report_regs)
    try:
        census = evaluate_census(predicates, payload)
    except ValueError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    if args.json:
        if census:
            payload["census"] = [item.as_dict() for item in census]
        print(json.dumps(payload, indent=2, sort_keys=True))
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
        print_census(census)
    mismatched = args.fail_on_mismatch and view.verdict not in {
        "exact",
        "words-identical",
    }
    return census_status(census, otherwise=1 if mismatched else 0)


def _symbol(args: argparse.Namespace) -> str | None:
    """Return the selected function.  ``--symbol`` and ``--function`` share it."""

    value = args.symbol
    return str(value) if value else None


def view_command(args: argparse.Namespace) -> int:
    """Render the aligned mechanism view for two object files."""

    symbol = _symbol(args)
    try:
        predicates = parse_census(args.census, allowed=VIEW_CENSUS_KEYS)
    except ValueError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
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
    return _emit(view, args, predicates)


def view_dumps_command(args: argparse.Namespace) -> int:
    """Render the aligned mechanism view from retained GNU objdump text."""

    symbol = _symbol(args)
    try:
        predicates = parse_census(args.census, allowed=VIEW_CENSUS_KEYS)
    except ValueError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
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
    return _emit(view, args, predicates)


def _add_shared_arguments(
    parser: argparse.ArgumentParser, *, object_inputs: bool = False
) -> None:
    """Add the view options, in the order ``compare`` establishes.

    Selector first, then the key registry, then how the inputs are read, then
    the rendering. Two commands that read the same two inputs should not present
    them in two different orders.
    """

    add_symbol_argument(
        parser,
        help_text="view only this exact symbol; --function is the same option",
    )
    add_explain_keys_argument(parser)
    if object_inputs:
        parser.add_argument(
            "--section", default=".text", help="object section (default: .text)"
        )
        parser.add_argument(
            "--objdump",
            help="GNU-compatible MIPS objdump; auto-detected when omitted",
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
    add_census_argument(parser)


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
    _add_shared_arguments(view_parser, object_inputs=True)
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
