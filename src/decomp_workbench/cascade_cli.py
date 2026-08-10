"""Command journey for the allocator decision cascade.

One family over one input -- a CDX log -- answering the questions five
hand-rolled campaign scripts answered separately and three answered wrongly:
what happened at this site, in every round; which colour was actually taken;
which occurrences pay which charge; which webs share a block; and, when a
reference object is supplied, whether the barrier a candidate is fighting
exists in the ROM at all.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from typing import Any

from .cascade import (
    RECORD_GRAMMAR,
    Cascade,
    CascadeError,
    CdxLog,
    Round,
    SaveDetail,
    block_report,
    color_order_report,
    cost_rows,
    parse_frame_offset,
    parse_row_range,
    rom_color_occupancy,
)
from .cli_options import add_symbol_argument
from .dis_cache import DisassemblyCache
from .frame_ladder import (
    SYMTAB_RECORD_GRAMMAR as SYMTAB_GRAMMAR,
)
from .frame_ladder import (
    frame_ladder,
    ladder_lines,
    op_report,
    parse_slot_names,
)
from .globalcolor import FP_COLOR_REGISTERS, register_for_color
from .row_source import load_dump_rows, load_object_rows
from .screen import build_screen_line
from .terminal import add_terminal_arguments, emit_lines

__all__ = ["register_cascade_commands"]

_CLASS_NAMES = {1: "integer", 2: "float"}

_ARITHMETIC_POINTER = (
    "The arithmetic these fields carry is specified in "
    "docs/p1-decision-arithmetic.md; the record grammar is "
    "`trace-cascade --grammar`."
)


class _GrammarAction(argparse.Action):
    """Print the record grammar and exit, like ``--version``."""

    def __init__(
        self, option_strings: Any, dest: str = argparse.SUPPRESS, **kwargs: Any
    ) -> None:
        super().__init__(
            option_strings=option_strings,
            dest=dest,
            default=argparse.SUPPRESS,
            nargs=0,
            **kwargs,
        )

    def __call__(
        self, parser: argparse.ArgumentParser, *args: Any, **kwargs: Any
    ) -> None:
        lines = [
            "CDX record grammar read by the cascade commands.",
            "",
            "SHIPPED records come from `decomp-workbench instrument-uopt`.",
            "CAMPAIGN-LOCAL records come from a uopt.c patch this project does",
            "not ship (WB-15): the workbench owns the reading, not the",
            "instrument. A log without them still gives rounds, colours, and",
            "the kill signal; the save arithmetic needs them.",
            "",
        ]
        for kind, description in (*RECORD_GRAMMAR.items(), *SYMTAB_GRAMMAR.items()):
            lines.append(f"[CDX] {kind}")
            lines.extend(f"    {line}" for line in _wrap(description, 68))
            lines.append("")
        lines.append(_ARITHMETIC_POINTER)
        print("\n".join(lines))
        parser.exit()


def _wrap(text: str, width: int) -> list[str]:
    words, lines, current = text.split(), [], ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if len(candidate) > width and current:
            lines.append(current)
            current = word
        else:
            current = candidate
    if current:
        lines.append(current)
    return lines


def _site_arguments(args: argparse.Namespace) -> dict[str, int | None]:
    """Turn the site options into exactly one keyed lookup."""

    if args.frame_offset is not None:
        named = parse_frame_offset(args.frame_offset)
        if args.slot is not None and args.frame is not None:
            # Both spellings resolve a site, so both must resolve the same
            # one. A driver that sets each from a different place and lets one
            # drift would otherwise get a plausible cascade for the wrong slot.
            derived = args.slot + args.frame
            if derived != named:
                raise CascadeError(
                    f"--frame-offset names frame offset {named} "
                    f"({named & 0xFFFFFFFF:#010x}), but --slot {args.slot} "
                    f"--frame {args.frame} derives {derived} "
                    f"({derived & 0xFFFFFFFF:#010x}). Name one site: drop "
                    "--frame-offset, or drop --frame and let --slot narrow "
                    "the screen line only."
                )
        return {
            "frame_offset": named,
            "symbol": args.symbol_id,
            "web": args.web,
        }
    # `--slot` is the sp-relative offset a screen line counts traffic at, and
    # it names the site too once the frame is known. Only the second use needs
    # `--frame`, so passing `--slot` alongside `--frame-offset` is a screen
    # narrowing, not a conflicting site.
    offset = None
    if args.slot is not None and (
        args.frame is not None or (args.symbol_id is None and args.web is None)
    ):
        if args.frame is None:
            raise CascadeError(
                "--slot is an sp-relative offset, so it needs --frame to name "
                "a site: --slot 1184 --frame -1704 is frame offset -520 "
                "(0xfffffdf8). The frame is the prologue's `addiu sp,sp,-N`, "
                "which `decomp-workbench score` prints. To use --slot only "
                "for the screen line, name the site another way."
            )
        offset = args.slot + args.frame
    return {"frame_offset": offset, "symbol": args.symbol_id, "web": args.web}


def _color(color: int | None) -> str:
    if color is None or color < 0:
        return "-"
    register = register_for_color(color)
    return f"c{color}/{register}" if register else f"c{color}"


def _colors(colors: tuple[int, ...]) -> str:
    return " ".join(_color(item) for item in colors) if colors else "-"


def _class_text(value: int | None) -> str:
    if value is None:
        return "class=?"
    return f"class={value}({_CLASS_NAMES.get(value, 'unknown')})"


def _detail_line(detail: SaveDetail | None, *, label: str) -> list[str]:
    if detail is None:
        return [
            f"  {label}: no savedetail record -- this log carries the shipped "
            "profile only, so the save arithmetic is not available"
        ]
    lines = [
        f"  {label}: gross {detail.gross:.3f} - chargeA {detail.charge_a:.3f} "
        f"- chargeB {detail.charge_b:.3f} = net {detail.net:.3f}"
        f"   over {detail.occurrence_count} occurrence(s), nocs {detail.nocs}"
    ]
    if detail.charge_b > 0:
        contributors = detail.charge_b_contributors
        if detail.charge_b_accounted:
            named = ", ".join(
                f"occ{item.index}@bb{item.block}x{item.weight:g}"
                for item in contributors
            )
            lines.append(
                f"    chargeB is a store-placement term (L92), paid by "
                f"{len(contributors)} occurrence(s): {named}"
            )
        elif detail.occurrences:
            lines.append(
                "    chargeB gate (L92) does not reproduce the recorded "
                f"{detail.charge_b:.3f} from this occurrence list; reporting "
                "the pass's number, not a derived attribution"
            )
    return lines


def _round_lines(item: Round, *, headroom: bool) -> list[str]:
    lines = [
        f"round {item.index}  w{item.web}  {_class_text(item.register_class)}  "
        f"decision={item.decision}  (trace decision #{item.ordinal})",
        f"  {item.inequality}",
        f"  save {item.save:.6f}  nocs {item.nocs}  regsleft "
        f"{item.registers_left if item.registers_left is not None else '-'}  "
        f"numintf {item.interference if item.interference is not None else '-'}",
        f"  natural {_color(item.natural_color)}   taken "
        f"{_color(item.resolved_color)}"
        + (
            "   <- the natural colour is NOT what the web got; "
            "`bestcolor` is the pre-resolution field"
            if item.resolution_differs
            else ""
        ),
        f"  forbidden {_colors(item.forbidden)}",
        f"  min-cost tie {_colors(item.mincost_tie)}",
    ]
    lines.extend(_detail_line(item.entering, label="entering"))
    for piece in item.pieces:
        lines.append(
            f"  piece left memory-resident: w{piece.web} net {piece.net:.3f} "
            f"(gross {piece.gross:.3f} chargeA {piece.charge_a:.3f} "
            f"chargeB {piece.charge_b:.3f}, {piece.occurrence_count} occ)"
        )
    if headroom and not item.declined and math.isfinite(item.deficit):
        lines.extend(_headroom_lines(item))
    return lines


def _headroom_lines(item: Round) -> list[str]:
    """What it would take to decline this web, in the pass's own units."""

    lines = [
        f"  headroom: net must fall by {item.deficit:.3f} to reach bestcost "
        f"{item.best_cost:.3f}. Only chargeA and chargeB can do it -- every "
        "term in gross is non-negative."
    ]
    detail = item.entering
    if detail is not None and detail.nocs:
        lines.append(
            f"    at nocs {detail.nocs}, removing occurrences lowers gross "
            "and therefore save (rank), and cannot raise it: the divisor "
            "floor is 2 (L29)."
        )
    return lines


def _cascade_lines(
    cascade: Cascade,
    *,
    occurrences: bool,
    costs: bool,
    headroom: bool,
) -> list[str]:
    site = cascade.site
    webs = ",".join(str(item) for item in site.webs)
    lines = [
        f"cascade: {cascade.name}  site={site.key}  "
        f"sym={site.symbol if site.symbol is not None else '-'}  webs={webs}",
        cascade.kill_line(),
    ]
    if site.caution:
        lines.append(f"CAUTION: {site.caution}")
    if not cascade.rounds:
        lines.append(
            "  no decision record for this site: the webs exist but p1 never "
            "reached them. That is a real outcome, not an empty result."
        )
    for item in cascade.rounds:
        lines.append("")
        lines.extend(_round_lines(item, headroom=headroom))
        if occurrences and item.entering is not None:
            lines.extend(_occurrence_lines(item.entering))
        if costs:
            lines.extend(_cost_lines(cascade, item))
    for piece in cascade.undecided:
        lines.append(
            f"\nundecided piece: w{piece.web} net {piece.net:.3f} "
            f"class={piece.piece_class} -- carved out and never decided"
        )
    for note in cascade.warnings:
        lines.append(f"\nwarning: {note}")
    return lines


def _occurrence_lines(detail: SaveDetail) -> list[str]:
    if not detail.occurrences:
        return [
            "  occurrences: no saveocc records for this round (campaign-local "
            "grammar; see --grammar)"
        ]
    lines = ["  occ   bb          uses defs weight term    nl o22 o23 w34  chargeB"]
    for item in detail.occurrences:
        lines.append(
            f"  {item.index:<5d} {item.block:<11d} {item.uses:<4d} "
            f"{item.defs:<4d} {item.weight:<6g} {item.term:<7g} "
            f"{item.nl:<2d} {item.o22:<3d} {item.o23:<3d} {item.w34:<3d}  "
            f"{'PAYS' if item.charges_b else '-'}"
        )
    return lines


def _cost_lines(cascade: Cascade, item: Round) -> list[str]:
    rows = cost_rows(cascade.costs.get(item.web, ()))
    if not rows:
        return ["  costs: no p1cost records for this web"]
    lines = ["  color      kind        cost"]
    for row in rows:
        name = _color(row["color"])
        cost = row["cost"]
        text = f"{cost:.3f}" if isinstance(cost, float) else str(cost)
        flag = "" if row["eligible"] else "  (ineligible sentinel)"
        lines.append(f"  {name:<10s} {row['kind']!s:<11s} {text}{flag}")
    return lines


def _rows(path: str, args: argparse.Namespace) -> list[Any]:
    """Read one side object, from the object or from retained dump text."""

    if args.dumps:
        return load_dump_rows(path, symbol=args.symbol)
    cache = DisassemblyCache(args.disassembly_cache) if args.disassembly_cache else None
    return load_object_rows(
        path,
        objdump=args.objdump,
        symbol=args.symbol,
        section=args.section,
        cache=cache,
    )


def _rom_lines(args: argparse.Namespace, cascade: Cascade) -> list[str]:
    """WB-69: name the colours the reference object never touches."""

    rows = parse_row_range(args.rom_rows) if args.rom_rows else None
    instructions = _rows(args.rom, args)
    report = rom_color_occupancy(
        instructions, colors=sorted(FP_COLOR_REGISTERS), rows=rows
    )
    lines = [
        "",
        f"reference object: {args.rom} rows {report['rows'][0]}..{report['rows'][1]}",
        "  float colours the reference uses:      "
        + (" ".join(_color(item["color"]) for item in report["present"]) or "-"),
        "  float colours the reference never uses: "
        + (" ".join(_color(item["color"]) for item in report["absent"]) or "-"),
    ]
    absent = {item["color"] for item in report["absent"]}
    for item in cascade.rounds:
        free = [color for color in item.mincost_tie if color in absent]
        blocked_but_absent = [color for color in item.forbidden if color in absent]
        if blocked_but_absent:
            lines.append(
                f"  round {item.index}: forbidden here but absent from the "
                f"reference: {_colors(tuple(blocked_but_absent))} -- the "
                "reference's own decision at this site cannot have been "
                "blocked by those colours, so a barrier hunt aimed at them "
                "is aimed at nothing."
            )
        if free:
            lines.append(
                f"  round {item.index}: cheapest-tie colours the reference "
                f"never uses: {_colors(tuple(free))}"
            )
    lines.append(f"  reading: {report['reading']}")
    return lines


def _screen_lines(args: argparse.Namespace) -> list[str]:
    """WB-78: loads AND stores at the slot, from the one shared screen line."""

    instructions = _rows(args.object, args)
    line = build_screen_line(
        instructions,
        label=args.object,
        # Retained dump text is not the object, so its digest would not be the
        # identity the line claims to carry. `sha=-` is the honest reading.
        path=None if args.dumps else args.object,
        slot=args.slot,
    )
    return ["", line.render()]


def _diff_lines(base: Cascade, other: Cascade) -> list[str]:
    lines = [
        f"cascade diff: {base.name} -> {other.name}  site={base.site.key}",
        f"  symbol {base.site.symbol} -> {other.site.symbol}"
        + (
            "   (renumbered -- which is why the site is keyed by frame offset)"
            if base.site.symbol != other.site.symbol
            else ""
        ),
        f"  rounds {len(base.rounds)} -> {len(other.rounds)}",
        f"  {base.kill_line()}",
        f"  {other.kill_line()}",
    ]
    if base.killed != other.killed:
        lines.append(
            "  VERDICT: the kill signal changed -- "
            f"{'killed' if base.killed else 'coloured'} in {base.name}, "
            f"{'killed' if other.killed else 'coloured'} in {other.name}"
        )
    sides = [
        (
            index + 1,
            _side(base.rounds[index] if index < len(base.rounds) else None),
            _side(other.rounds[index] if index < len(other.rounds) else None),
        )
        for index in range(max(len(base.rounds), len(other.rounds)))
    ]
    width = max([len("A"), *(len(item[1]) for item in sides)]) if sides else 1
    other_width = max([len("B"), *(len(item[2]) for item in sides)]) if sides else 1
    lines.append("")
    lines.append(f"  round  {'A'.ljust(width)}  {'B'.ljust(other_width)}  changed")
    for index, left, right in sides:
        item = base.rounds[index - 1] if index <= len(base.rounds) else None
        against = other.rounds[index - 1] if index <= len(other.rounds) else None
        lines.append(
            f"  {index:<6d} {left.ljust(width)}  {right.ljust(other_width)}  "
            f"{_changed(item, against)}"
        )
    return lines


def _side(item: Round | None) -> str:
    if item is None:
        return "-"
    return f"w{item.web}:{item.decision}:{_color(item.resolved_color)}"


def _changed(left: Round | None, right: Round | None) -> str:
    if left is None or right is None:
        return "present in one side only"
    changed = []
    for name, one, two in (
        ("decision", left.decision, right.decision),
        ("taken", left.resolved_color, right.resolved_color),
        ("net", round(left.net, 6), round(right.net, 6)),
        ("bestcost", round(left.best_cost, 6), round(right.best_cost, 6)),
        ("numintf", left.interference, right.interference),
        ("forbidden", left.forbidden, right.forbidden),
    ):
        if one != two:
            changed.append(name)
    return ",".join(changed) if changed else "same"


def cascade_command(args: argparse.Namespace) -> int:
    try:
        log = CdxLog.read(args.log)
        site = log.resolve(**_site_arguments(args))
        cascade = log.cascade(site)
        against = None
        if args.against:
            other_log = CdxLog.read(args.against)
            against = other_log.cascade(other_log.resolve(**_site_arguments(args)))
    except CascadeError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    except (OSError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2

    if args.kill and not args.json:
        print(cascade.kill_line())
        if against is not None:
            print(against.kill_line())
        return 0

    try:
        extra: list[str] = []
        if args.rom:
            extra.extend(_rom_lines(args, cascade))
        if args.object:
            extra.extend(_screen_lines(args))
    except (CascadeError, OSError, RuntimeError, ValueError) as error:
        # --rom and --object reach objdump, which raises RuntimeError with the
        # file named and the tool quoted. The cascade itself already read; an
        # unreadable reference object refuses the run rather than crashing it.
        print(f"error: {error}", file=sys.stderr)
        return 2

    if args.json:
        payload: dict[str, Any] = cascade.as_dict()
        if against is not None:
            payload["against"] = against.as_dict()
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0

    if against is not None:
        lines = _diff_lines(cascade, against)
    else:
        lines = _cascade_lines(
            cascade,
            occurrences=args.occurrences,
            costs=args.costs,
            headroom=args.headroom,
        )
    lines.extend(extra)
    emit_lines(lines, width=args.width, pager=args.pager)
    return 0


def order_command(args: argparse.Namespace) -> int:
    try:
        log = CdxLog.read(args.log)
        report = color_order_report(
            log, limit=args.limit, register_class=args.register_class
        )
    except (CascadeError, OSError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0
    lines = [
        f"colour order: {report['log']}  {report['shown']} of "
        f"{report['decision_count']} decision(s)"
        + (
            f"  class={report['register_class']}"
            f"({_CLASS_NAMES.get(report['register_class'], '?')})"
            if report["register_class"] is not None
            else ""
        ),
        " pos    web    sym   save        nocs  net       bestcost  colour       "
        "numintf  decision",
    ]
    for item in report["order"]:
        save = item["save"]
        net = item["net"]
        cost = item["best_cost"]
        lines.append(
            f" {item['position']:<6d} {item['web']!s:<6s} "
            f"{item['symbol']!s:<5s} "
            f"{save if isinstance(save, str) else f'{save:<11.6f}'} "
            f"{item['nocs']!s:<5s} "
            f"{net if isinstance(net, str) else f'{net:<9.3f}'} "
            f"{cost if isinstance(cost, str) else f'{cost:<9.3f}'} "
            f"{_color(item['color']):<12s} "
            f"{item['interference']!s:<8s} {item['decision']}"
        )
    if report["tie_groups"]:
        lines.append("")
        lines.append(
            "ties (p1 breaks these by ASCENDING web number, so a threshold "
            "against a lower-numbered web is >=, not > -- L31):"
        )
        for group in report["tie_groups"]:
            members = ", ".join(
                f"pos{item['position']}/w{item['web']}" for item in group["members"]
            )
            lines.append(f"  save={group['save']:.6f}: {members}")
    else:
        lines.append("")
        lines.append("ties: none in the shown range")
    emit_lines(lines, width=args.width, pager=args.pager)
    return 0


def blocks_command(args: argparse.Namespace) -> int:
    try:
        log = CdxLog.read(args.log)
        report = block_report(log, webs=args.web, blocks=args.block)
    except (CascadeError, OSError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0
    queried = ",".join(str(item) for item in report["queried_blocks"])
    lines = [
        f"web blocks: {report['log']}  {len(report['webs'])} web(s)"
        + (f"  queried blocks {queried}" if queried else "")
    ]
    for entry in report["webs"]:
        blocks = " ".join(str(item) for item in entry["blocks"])
        lines.append(f"  w{entry['web']}  {entry['block_count']} block(s): {blocks}")
    if len(report["webs"]) > 1:
        if report["intersection"]:
            shared = " ".join(str(item) for item in report["intersection"])
            lines.append(
                f"  intersection: {len(report['intersection'])} block(s): {shared}"
            )
            lines.append(
                "  These webs occur in the same blocks. Interference argued "
                "from a numintf delta alone is argued from a summary; this is "
                "the set."
            )
        else:
            lines.append(
                "  intersection: EMPTY -- these webs share no occurrence "
                "block, so neither can be blocking the other through a "
                "shared block."
            )
    emit_lines(lines, width=args.width, pager=args.pager)
    return 0


def frame_command(args: argparse.Namespace) -> int:
    """Print one procedure's frame ladder, or its itable operation stream."""

    try:
        log = CdxLog.read(args.log)
        names: dict[int, str] = {}
        if args.names:
            from pathlib import Path

            try:
                text = Path(args.names).read_text(encoding="utf-8")
            except OSError as error:
                raise CascadeError(f"cannot read {args.names}: {error}") from None
            names = parse_slot_names(text, frame=args.frame)
        ladder = frame_ladder(log, frame=args.frame, proc=args.proc, names=names)
        operations = op_report(ladder, names=names) if args.ops else None
    except CascadeError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    if args.json:
        document: dict[str, Any] = ladder.as_dict()
        if operations is not None:
            document["operations"] = operations
        print(json.dumps(document, indent=2, sort_keys=True))
        return 0
    if args.summary:
        lines = [
            f"frame ladder: {ladder.log}  {len(ladder.slots)} slot(s)  "
            f"named={len(ladder.named)} unnamed="
            f"{len(ladder.slots) - len(ladder.named)}  "
            f"source={'+'.join(ladder.sources)}",
            f"  lowest offset {ladder.slots[0].offset if ladder.slots else '-'}"
            f"  lowest named {ladder.lowest_named_offset if ladder.named else '-'}"
            f"  temps below it {len(ladder.below_named)}",
            f"  itable entries {len(ladder.entries)}, of which "
            f"{sum(item.is_operation for item in ladder.entries)} operation(s)",
        ]
        for warning in ladder.warnings:
            lines.append(f"warning: {warning}")
        emit_lines(lines, width=args.width, pager=args.pager)
        return 0
    lines = list(ladder_lines(ladder))
    if operations is not None:
        lines.append(
            f"itable operations: {operations['selected_count']} of "
            f"{operations['entry_count']} entries, in first-occurrence order"
        )
        for row in operations["operations"][: args.limit]:
            lines.append(
                f"  op{row['index']:<5d} {row['opcode_name']:<6s} "
                f"l={row['left_name']:<20s} r={row['right_name']:<20s} "
                f"dt={row['dtype']}"
            )
        if operations["selected_count"] > args.limit:
            lines.append(
                f"  ... {operations['selected_count'] - args.limit} more "
                "operation(s); raise --limit"
            )
    emit_lines(lines, width=args.width, pager=args.pager)
    return 0


def _add_site_arguments(parser: argparse.ArgumentParser) -> None:
    site = parser.add_argument_group(
        "site",
        "Name exactly one site. Prefer the frame offset: it is the only "
        "identity in the grammar that a rebase does not move.",
    )
    site.add_argument(
        "--frame-offset",
        metavar="OFFSET",
        help=(
            "the web's frame offset, as the trace prints it (0xfffffdf8) or "
            "signed (-520)"
        ),
    )
    site.add_argument(
        "--slot",
        type=lambda value: int(value, 0),
        metavar="OFFSET",
        help="sp-relative slot offset; needs --frame to become a frame offset",
    )
    site.add_argument(
        "--frame",
        type=lambda value: int(value, 0),
        metavar="SIZE",
        help="the frame size, signed, as the prologue's addiu sp,sp,-N writes it",
    )
    site.add_argument(
        "--web",
        type=int,
        metavar="N",
        help="a trace-local web number (changes with any edit that adds a live range)",
    )
    site.add_argument(
        "--symbol-id",
        type=int,
        metavar="N",
        help=(
            "a trace-local symbol number. Accepted, and cautioned: one "
            "campaign's sym=1042 became sym=1039 on a rebase and the script "
            "that grepped the old number reported a kill that never happened"
        ),
    )


def register_cascade_commands(commands: argparse._SubParsersAction[Any]) -> None:
    """Register ``trace-cascade``, ``trace-order``, and ``trace-blocks``."""

    cascade = commands.add_parser(
        "trace-cascade",
        help="every round of one allocator site's decision cascade",
        description=(
            "Print the whole decision trail for one web family from a CDX "
            "log: every round of an f_split cascade, not just the last; the "
            "colour the web actually received, not the pre-resolution "
            "`bestcolor`; and the decision as the one inequality it is. "
            "Sites are located by frame offset, which survives the "
            "renumbering that made a hard-coded symbol number report false "
            "kills for seven stages of one campaign. " + _ARITHMETIC_POINTER
        ),
        epilog=(
            "example: decomp-workbench trace-cascade build.ilog "
            "--frame-offset 0xfffffdf8 --occurrences"
        ),
    )
    cascade.add_argument("log", help="CDX log from an instrumented build")
    cascade.add_argument(
        "--against",
        metavar="LOG",
        help="second log; report the same site's cascade in both, round by round",
    )
    _add_site_arguments(cascade)
    cascade.add_argument(
        "--occurrences",
        action="store_true",
        help=(
            "also print each round's occurrence table with the chargeB gate "
            "marked (bb weight nl o22 o23 w34 uses defs)"
        ),
    )
    cascade.add_argument(
        "--costs",
        action="store_true",
        help="also print the per-colour cost sweep behind each decision",
    )
    cascade.add_argument(
        "--headroom",
        action="store_true",
        help="also print how far net must fall for each coloured web to be declined",
    )
    cascade.add_argument(
        "--kill",
        action="store_true",
        help=(
            "print only the one-line kill signal, for a sweep column. "
            "--json is unaffected: it always emits the whole cascade "
            "document, whose `killed` and `kill_line` fields carry this "
            "same signal"
        ),
    )
    cascade.add_argument(
        "--rom",
        metavar="OBJECT",
        help=(
            "reference object -- a compiled `.o`, not a ROM image; the "
            "command that reads a ROM image is `score --rom`. Report which "
            "float colours it never uses, so a "
            "forbidden set can be checked against the allocation the "
            "reference actually made"
        ),
    )
    cascade.add_argument(
        "--rom-rows",
        metavar="LO..HI",
        help="restrict the reference reading to these rows (inclusive)",
    )
    cascade.add_argument(
        "--object",
        metavar="OBJECT",
        help="candidate object; print its screen line, loads and stores apart",
    )
    cascade.add_argument(
        "--dumps",
        action="store_true",
        help=(
            "--rom and --object name retained `objdump -d -r` text rather than "
            "objects, for a reader who kept the dumps"
        ),
    )
    cascade.add_argument(
        "--section", default=".text", help="object section (default: .text)"
    )
    cascade.add_argument(
        "--objdump", help="GNU-compatible MIPS objdump; auto-detected when omitted"
    )
    cascade.add_argument(
        "--disassembly-cache",
        metavar="DIR",
        help="reuse disassemblies from this directory across runs",
    )
    add_symbol_argument(
        cascade, help_text="read only this exact symbol from --rom/--object"
    )
    cascade.add_argument(
        "--grammar",
        action=_GrammarAction,
        help="print the CDX record grammar these commands read, and exit",
    )
    cascade.add_argument("--json", action="store_true", help="emit JSON")
    add_terminal_arguments(cascade)
    cascade.set_defaults(handler=cascade_command, report_command="trace-cascade")

    order = commands.add_parser(
        "trace-order",
        help="rank the p1 colouring order, with the same-save ties named",
        description=(
            "Print the order p1 decides webs in, with each web's save, net, "
            "bestcost, colour and interference count, and the groups that "
            "tie on save. `--class 2` is the float census: every float web in "
            "the object, in decision order, in one pass. " + _ARITHMETIC_POINTER
        ),
        epilog="example: decomp-workbench trace-order build.ilog --class 2 --limit 40",
    )
    order.add_argument("log", help="CDX log from an instrumented build")
    order.add_argument(
        "--limit", type=int, default=40, metavar="N", help="rows to show (default: 40)"
    )
    order.add_argument(
        "--class",
        dest="register_class",
        type=int,
        choices=(1, 2),
        help="restrict to one register class: 1 integer, 2 float",
    )
    order.add_argument("--json", action="store_true", help="emit JSON")
    add_terminal_arguments(order)
    order.set_defaults(handler=order_command, report_command="trace-order")

    blocks = commands.add_parser(
        "trace-blocks",
        help="which webs occur in which basic blocks, and where the sets meet",
        description=(
            "Print each web's occurrence-block set and their intersection. "
            "'Which web interferes with which' is a set intersection over "
            "`saveocc bb=` values; one campaign argued it from numintf deltas "
            "across five stages and resolved it in one command once the sets "
            "were printed."
        ),
        epilog="example: decomp-workbench trace-blocks build.ilog --web 255 --web 260",
    )
    blocks.add_argument("log", help="CDX log from an instrumented build")
    blocks.add_argument(
        "--web",
        type=int,
        action="append",
        default=[],
        metavar="N",
        help="a web to report; repeatable",
    )
    blocks.add_argument(
        "--block",
        type=lambda value: int(value, 0),
        action="append",
        default=[],
        metavar="BB",
        help="report every web occurring in this block; repeatable",
    )
    blocks.add_argument("--json", action="store_true", help="emit JSON")
    add_terminal_arguments(blocks)
    blocks.set_defaults(handler=blocks_command, report_command="trace-blocks")

    frame = commands.add_parser(
        "trace-frame",
        help="the frame ladder: every stack slot one procedure owns",
        description=(
            "Print one procedure's stack slots, lowest offset first, with the "
            "sp-relative home each one has, the itable index stamped at it, "
            "and the allocator webs that reached it. Names are yours to "
            "supply with --names: the input ucode carries none, so no "
            "instrument can print one. --ops adds the itable's operation "
            "stream in first-occurrence order, which is where a pooled "
            "compiler temp's birth site can be read."
        ),
        epilog=(
            "example: decomp-workbench trace-frame build.ilog --frame -216 "
            "--names locals.txt"
        ),
    )
    frame.add_argument("log", help="CDX log from an instrumented build")
    frame.add_argument(
        "--frame",
        type=lambda value: int(value, 0),
        metavar="SIZE",
        help=(
            "the frame size, signed, as the prologue's addiu sp,sp,-N writes "
            "it; turns each offset into the sp-relative home a disassembly "
            "shows"
        ),
    )
    frame.add_argument(
        "--proc",
        type=int,
        metavar="N",
        help="restrict to one procedure ordinal (default: every procedure)",
    )
    frame.add_argument(
        "--names",
        metavar="FILE",
        help=(
            "reader-supplied slot names, one `OFFSET NAME` per line; `-140 "
            "colour` is a frame offset and `sp:76 colour` an sp-relative slot"
        ),
    )
    frame.add_argument(
        "--ops",
        action="store_true",
        help=(
            "also print the itable's operation stream with symbolic operands "
            "(needs CDX_SYMTAB records)"
        ),
    )
    frame.add_argument(
        "--summary",
        action="store_true",
        help="print the slot counts only, for a sweep column",
    )
    frame.add_argument(
        "--limit", type=int, default=80, metavar="N", help="operations to show"
    )
    frame.add_argument("--json", action="store_true", help="emit JSON")
    add_terminal_arguments(frame)
    frame.set_defaults(handler=frame_command, report_command="trace-frame")
