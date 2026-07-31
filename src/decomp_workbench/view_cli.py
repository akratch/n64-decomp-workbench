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
from .force_spec import write_force_specification
from .html_report import render_diagnosis_html
from .model import Instruction, display_path
from .objdump import (
    cross_function_warning,
    dump_object,
    parse_disassembly,
    symbol_selection_error,
)
from .schema import VIEW_CENSUS_KEYS
from .terminal import (
    WEB_COLORS,
    Painter,
    add_color_argument,
    add_terminal_arguments,
    emit_lines,
    resolve_color,
    resolve_width,
    visible_length,
    visible_ljust,
)
from .view import (
    DEFAULT_REGISTER_PROFILE,
    MATCH,
    REGISTER_CLASS_PROFILES,
    AlignedRow,
    Hunk,
    MechanismView,
    build_view,
)

# `Painter` and `resolve_color` moved to `terminal`, beside the width and pager
# controls they share a screen with, once `compare` needed them too. They are
# re-exported here because this is where every caller already looked.
__all__ = [
    "WEB_COLORS",
    "Painter",
    "add_view_output_arguments",
    "add_view_render_arguments",
    "register_view_commands",
    "render_view",
    "resolve_color",
]


def _tokens(pairs: Sequence[tuple[str, object]]) -> str:
    return " ".join(f"{key}={value}" for key, value in pairs)


def _range(value: tuple[int, int] | None) -> str:
    return "none" if value is None else f"{value[0]}..{value[1]}"


def _byte_range(value: tuple[int, int] | None) -> str:
    return "none" if value is None else f"0x{value[0]:x}..0x{value[1]:x}"


def _cell(text: str | None, width: int) -> str:
    """Render one assembly column, padded but never truncated."""

    return ("-" if text is None else text).ljust(width)


#: One-time orientation lines: true for every run, useful on the first few.
#:
#: They are printed by default because the reader who needs them cannot know
#: to ask, and suppressed by `--terse` because the reader who does not need
#: them meets this screen hundreds of times in a campaign.
SIGNATURE_NOTE = (
    "signature reads left to right: how much is untouched, where state first "
    "drifts, then which axis it drifted on - in that causal order."
)
LANE_NOTE = (
    "pool = uopt's colored variable webs (lowest free index wins); "
    "temp = ugen's block-local FIFO rotation (t6-t9, s8) - two independent "
    "register populations that diverge independently."
)
KEY_NOTE = "labels defined: decomp-workbench --explain-keys"


def render_header(
    view: MechanismView,
    painter: Painter | None = None,
    *,
    terse: bool = False,
) -> list[str]:
    brush = painter or Painter(False)
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
    lines.append(
        brush.bold("verdict:")
        + " "
        + brush.verdict(view.verdict)
        + "  "
        + _tokens(verdict_tokens)
    )
    lines.append("signature: " + " ".join(view.signature))
    if not terse:
        lines.append("  " + SIGNATURE_NOTE)
    # The bijection is the highest-leverage fact on the screen and used to sit
    # below every hunk, where a reader who stopped at the first divergence
    # never reached it. The full table stays where it is; this is the index.
    if view.webs:
        summary = ", ".join(
            brush.web(number, f"{web.web} {web.target}->{web.candidate} x{web.count}")
            for number, web in enumerate(view.webs, 1)
        )
        lines.append("webs: " + summary)
    if not terse:
        lines.append(KEY_NOTE)
    return lines


def render_lanes(view: MechanismView, *, window: int, terse: bool = False) -> list[str]:
    if not view.lanes:
        return []
    lines = [
        "",
        "REGISTER LANES (per-class assignment sequences, matching instructions "
        "included)",
    ]
    if not terse:
        lines.append("  " + LANE_NOTE)
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
        # Two different units used to be spelled `divergence=5 index=12`,
        # which read as one coordinate pair. `slot` counts positions in this
        # lane; `aligned_row` counts rows of the alignment, the same unit the
        # header's `aligned_rows` and every hunk range use.
        detail: list[tuple[str, object]] = [
            ("slot", lane.divergence),
            ("aligned_row", lane.divergence_row),
        ]
        if lane.rotation:
            detail.append(("rotation", f"+{lane.rotation}"))
        lines.append(f"{marker_indent}{'-' * offset}^ " + _tokens(detail))
    return lines


def _annotation_parts(
    row: AlignedRow, webs: dict[tuple[str, str], int], painter: Painter
) -> list[str]:
    """Return one label per substitution, kept separable for wrapping."""

    parts = []
    for pair in row.substitutions:
        number = webs.get(pair)
        label = f"{pair[0]}->{pair[1]}"
        if number is not None:
            label = painter.web(number, f"{label} [w{number}]")
        parts.append(label)
    return parts


def _annotation(
    row: AlignedRow, webs: dict[tuple[str, str], int], painter: Painter
) -> str:
    return " ".join(_annotation_parts(row, webs, painter))


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
    budget: int = 0,
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
            _render_hunk_rows(
                view,
                hunk,
                window=window,
                webs=webs,
                painter=painter,
                budget=budget,
            )
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


#: Columns consumed by ``"  12345 > "`` before the first assembly cell.
ROW_PREFIX = 2 + 5 + 1 + 1 + 1

#: Where a wrapped annotation restarts. Deep enough to read as a continuation
#: of the row above rather than as a new row.
ANNOTATION_INDENT = " " * (ROW_PREFIX + 2)


def _paint_registers(
    text: str | None,
    registers: Sequence[str],
    row: AlignedRow,
    webs: dict[tuple[str, str], int],
    painter: Painter,
    *,
    target_side: bool,
) -> str:
    """Colour the substituted register tokens inside the disassembly itself.

    The trailing ``t7->t8 [w1]`` says which registers moved; it does not say
    *where* in a sixty-column instruction they are. Painting the token in its
    web's own colour puts the answer under the reader's eye, and the two sides
    of one substitution then share a hue across the ``|``.
    """

    rendered = "-" if text is None else text
    if not painter.enabled or text is None:
        return rendered
    for pair in row.substitutions:
        number = webs.get(pair)
        if number is None:
            continue
        register = pair[0] if target_side else pair[1]
        if register not in registers:
            continue
        for token in (f"${register}", register):
            index = rendered.find(token)
            if index < 0:
                continue
            # Only a whole operand token: `$t1` must never match inside `$t10`.
            trailing = rendered[index + len(token) : index + len(token) + 1]
            if trailing.isalnum():
                continue
            rendered = (
                rendered[:index]
                + painter.web(number, token)
                + rendered[index + len(token) :]
            )
            break
    return rendered


def _render_hunk_rows(
    view: MechanismView,
    hunk: Hunk,
    *,
    window: tuple[int, int],
    webs: dict[tuple[str, str], int],
    painter: Painter,
    budget: int = 0,
) -> list[str]:
    start, end = window
    rows = view.rows[start : end + 1]
    width = _assembly_width(rows)
    lines: list[str] = []
    for row in rows:
        inside = hunk.start <= row.index <= hunk.end
        marker = ">" if inside else " "
        # Every non-matched row gets its substitution named, in or out of this
        # hunk. A context row whose swap belongs to a known web used to print
        # a bare `register`, which reads as an unexplained site sitting beside
        # the explained ones -- the exact opposite of what a web is for. The
        # `>` marker, not the annotation, is what separates this hunk's rows
        # from the evidence around them.
        parts = _annotation_parts(row, webs, painter) if not row.matched else []
        if not parts and not row.matched:
            # A displacement never opens a hunk and carries no substitution,
            # and it must still be visible where it happens.
            parts = [row.classification]
        target = _paint_registers(
            row.target, row.target_registers, row, webs, painter, target_side=True
        )
        candidate = _paint_registers(
            row.candidate,
            row.candidate_registers,
            row,
            webs,
            painter,
            target_side=False,
        )
        body = (
            f"  {row.index:5d} {marker} "
            f"{visible_ljust(target, width)} | "
            f"{visible_ljust(candidate, width)}"
        )
        lines.extend(_wrap_annotation(body, parts, budget))
    return lines


def _wrap_annotation(body: str, parts: Sequence[str], budget: int) -> list[str]:
    """Attach the annotation to `body`, wrapping rather than losing any of it.

    `--width` truncates from the right, so a narrow terminal used to cut a
    row's second web tag off silently -- a verdict suppressing its own
    evidence, which is the one thing this tool promises never to do. The
    assembly columns may be cut by the width the reader asked for; the
    annotation moves to a continuation line instead.
    """

    if not parts:
        return [body]
    joined = " ".join(parts)
    if not budget or visible_length(body) + 2 + visible_length(joined) <= budget:
        return [f"{body}  {joined}"]
    lines = [body]
    current = ANNOTATION_INDENT
    for part in parts:
        candidate = current + (" " if current != ANNOTATION_INDENT else "") + part
        if current != ANNOTATION_INDENT and visible_length(candidate) > budget:
            lines.append(current)
            current = ANNOTATION_INDENT + part
        else:
            current = candidate
    lines.append(current)
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
    show_warnings: bool = True,
    width: int = 0,
    terse: bool = False,
    extra_sections: Sequence[str] = (),
) -> list[str]:
    """Render the whole screen as lines of monochrome-safe text.

    `show_warnings=False` is for `diagnose`, which owns a screen holding two
    reports built from the same inputs and would otherwise print one input
    warning twice.

    `extra_sections` are already-rendered blocks belonging to an opt-in input
    this module does not read -- today, the statement-line evidence a ugen
    listing supplies. They land after the evidence and before the footer,
    because the footer is the instruction and must stay last on the screen.
    """

    brush = painter or Painter(False)
    lines = (
        [f"warning: {warning}" for warning in view.warnings] if show_warnings else []
    )
    lines.extend(render_header(view, brush, terse=terse))
    if view.register_first_divergence:
        lines.append(
            brush.warn(
                "the FIRST divergence is a register-class divergence, not a "
                "structural one: the decision was made upstream of hunk 1 even "
                "though it surfaces there."
            )
        )
    lines.extend(render_lanes(view, window=lane_window, terse=terse))
    lines.extend(
        render_hunks(
            view,
            context=context,
            max_hunks=max_hunks,
            painter=brush,
            budget=resolve_width(width),
        )
    )
    lines.extend(render_webs(view, painter=brush))
    if report_regs:
        lines.extend(render_register_report(view))
    lines.extend(extra_sections)
    lines.append("")
    lines.extend(render_guidance(view.guidance, budget=resolve_width(width)))
    return [line.rstrip() for line in lines]


def render_guidance(guidance: Sequence[str], *, budget: int = 0) -> list[str]:
    """Render the `next:` footer, wrapping rather than ellipsizing.

    This block is the instruction the whole screen exists to deliver, and it
    carries the dead-family warnings that stop the next round being wasted. At
    a bounded width `emit_lines` was cutting it from the right, so the sentence
    that survived was the setup and the one that vanished was the point. Prose
    wraps on word boundaries; an indented sub-line keeps its own indent so the
    lever list stays a list.
    """

    lines: list[str] = []
    for position, entry in enumerate(guidance):
        indent = " " * (len(entry) - len(entry.lstrip(" ")))
        lead = ("next: " if position == 0 else "      ") + indent
        lines.extend(_wrap_words(entry.strip(), lead=lead, budget=budget))
    return lines


def _wrap_words(text: str, *, lead: str, budget: int) -> list[str]:
    """Wrap `text` under `lead`, on spaces, never dropping a word.

    Continuation lines sit two columns inside the first, so a wrapped sentence
    cannot be mistaken for the next guidance entry.
    """

    if not budget or visible_length(lead) + visible_length(text) <= budget:
        return [lead + text]
    continuation = " " * (len(lead) + 2)
    lines: list[str] = []
    current = lead
    for word in text.split(" "):
        if not word:
            continue
        candidate = current + ("" if current in {lead, continuation} else " ") + word
        if current not in {lead, continuation} and visible_length(candidate) > budget:
            lines.append(current)
            current = continuation + word
        else:
            current = candidate
    lines.append(current)
    return lines


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------


def _emit(
    view: MechanismView,
    args: argparse.Namespace,
    predicates: Sequence[Predicate] = (),
) -> int:
    if args.json and args.html:
        print("error: --json and --html are mutually exclusive", file=sys.stderr)
        return 2
    # The payload is only built when something reads it: the human rendering
    # walks the view itself, and `--report-regs` makes this a per-row list.
    payload = (
        view.as_dict(report_regs=args.report_regs) if args.json or predicates else {}
    )
    try:
        census = evaluate_census(predicates, payload)
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
            write_force_specification(view, force_output)
        if html_output is not None:
            html_output.parent.mkdir(parents=True, exist_ok=True)
            with html_output.open("x", encoding="utf-8") as destination:
                destination.write(render_diagnosis_html(view))
            print(
                f"note: {html_output} contains the target's disassembly. "
                "It is ROM-derived -- keep it out of version control.",
                file=sys.stderr,
            )
    except (OSError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    if args.json:
        if census:
            payload["census"] = [item.as_dict() for item in census]
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        painter = Painter(resolve_color(args.color))
        lines = render_view(
            view,
            context=args.context,
            max_hunks=args.max_hunks,
            lane_window=args.lane_window,
            report_regs=args.report_regs,
            painter=painter,
            width=args.width,
            terse=args.terse,
        )
        lines.extend(item.line for item in census)
        if args.html:
            lines.append(f"HTML report: {Path(args.html).expanduser().resolve()}")
        if args.emit_force_spec:
            lines.append(
                "diagnostic force specification: "
                f"{Path(args.emit_force_spec).expanduser().resolve()}"
            )
        emit_lines(lines, width=args.width, pager=args.pager)
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
        target_text, target = dump_object(
            args.target, objdump=args.objdump, symbol=symbol, section=args.section
        )
        candidate_text, candidate = dump_object(
            args.candidate, objdump=args.objdump, symbol=symbol, section=args.section
        )
        warning = cross_function_warning(
            target_text,
            candidate_text,
            symbol=symbol,
            section=args.section,
        )
        view = build_view(
            target,
            candidate,
            target_name=display_path(args.target),
            candidate_name=display_path(args.candidate),
            symbol=symbol,
            register_profile=args.register_profile,
            warnings=(warning,) if warning else (),
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
        print(
            "error: "
            + symbol_selection_error(
                symbol,
                inputs=(
                    (display_path(args.target), target_text),
                    (display_path(args.candidate), candidate_text),
                ),
            ),
            file=sys.stderr,
        )
        return 2
    warning = cross_function_warning(target_text, candidate_text, symbol=symbol)
    try:
        view = build_view(
            target,
            candidate,
            target_name=display_path(args.target),
            candidate_name=display_path(args.candidate),
            symbol=symbol,
            register_profile=args.register_profile,
            warnings=(warning,) if warning else (),
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
    add_view_render_arguments(parser)
    add_view_output_arguments(parser)
    parser.add_argument(
        "--fail-on-mismatch",
        action="store_true",
        help="return exit 1 unless the verdict is exact or words-identical",
    )
    add_census_argument(parser)


def add_view_render_arguments(
    parser: argparse.ArgumentParser,
    *,
    default_max_hunks: int = 20,
) -> None:
    """Add the aligned-view presentation controls to another command."""

    parser.add_argument(
        "--report-regs",
        action="store_true",
        help="report per-aligned-index register operands, matching rows included",
    )
    parser.add_argument(
        "--terse",
        action="store_true",
        help="drop the one-line orientation notes; every label and count stays",
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
        default=default_max_hunks,
        help=(f"maximum hunks to render; 0 renders all (default: {default_max_hunks})"),
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
    add_color_argument(parser)


def add_view_output_arguments(parser: argparse.ArgumentParser) -> None:
    """Add terminal and share/export controls for a complete view command."""

    add_terminal_arguments(parser)
    parser.add_argument(
        "--html",
        metavar="PATH",
        help="write a self-contained aligned evidence report",
    )
    parser.add_argument(
        "--emit-force-spec",
        metavar="PATH",
        help="write an honest register-permutation oracle handoff",
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
