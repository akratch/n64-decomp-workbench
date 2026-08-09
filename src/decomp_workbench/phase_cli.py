"""Command journey for the ring-phase profiler."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

from .cli_options import add_explain_keys_argument, add_symbol_argument
from .dis_cache import DisassemblyCache
from .model import Instruction, display_path, shorten_paths
from .phase import (
    COSET_FAMILIES,
    DEFAULT_RING,
    MAX_ALL_RING,
    PhaseError,
    PhaseReport,
    Slot,
    build_phase_report,
    parse_ring,
    parse_slots,
    phase_lines,
)
from .row_source import load_dump_rows, load_object_rows
from .shift_align import (
    ALIGNMENT_GRANULARITIES,
    DEFAULT_GRANULARITY,
    build_shift_diff,
)
from .terminal import add_terminal_arguments, emit_lines

__all__ = ["phase_command", "register_phase_commands"]

#: JSON identity for a multi-candidate run.
PHASE_CENSUS_SCHEMA = "decomp-workbench-phase-census-v1"


def _read_slots(args: argparse.Namespace) -> tuple[Slot, ...] | None:
    """Return the slot table, from the flag or the file, or ``None``."""

    if args.slots and args.slots_from:
        raise PhaseError(
            "--slots and --slots-from both name the slot table; pass one of them"
        )
    if args.slots:
        return parse_slots(args.slots)
    if args.slots_from:
        # A file, because a newline-joined shell variable does not word-split
        # under zsh: one campaign's whole slot list arrived as a single
        # argument and died inside objdump with a "file name too long" error
        # that read as a scorer bug.
        text = Path(args.slots_from).read_text(encoding="utf-8")
        entries = [line.split("#", 1)[0].strip() for line in text.splitlines()]
        return parse_slots(",".join(entry for entry in entries if entry))
    return None


def _rows(
    path: str, args: argparse.Namespace, *, cache: DisassemblyCache | None
) -> list[Instruction]:
    if getattr(args, "dumps", False):
        return load_dump_rows(path, symbol=args.symbol)
    return load_object_rows(
        path,
        objdump=args.objdump,
        symbol=args.symbol,
        section=args.section,
        cache=cache,
    )


def _base_identity(args: argparse.Namespace) -> tuple[str | None, str | None]:
    """Return the declared base source and its SHA-256, checking the pin.

    A band scorer will happily score an object built from base A against a
    table of objects built from base B and print a number that looks like an
    improvement. Stamping the base the run was made against, and refusing when
    it is not the one the caller pinned, is the whole fix.
    """

    if not args.base:
        if args.require_base:
            raise PhaseError(
                "--require-base needs --base SOURCE to check against; pass the "
                "source file this candidate was built from"
            )
        return None, None
    path = Path(args.base)
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if args.require_base and not digest.startswith(args.require_base.lower()):
        raise PhaseError(
            f"--base {display_path(path)} has sha256 {digest}, which does not "
            f"start with the pinned --require-base {args.require_base}. These "
            "candidates were built from a different base than the table you "
            "are comparing them with; rebuild, or drop the pin deliberately."
        )
    return display_path(path), digest


def _check_instruction_count(report: PhaseReport, *, strict: bool) -> str | None:
    """Refuse or flag a candidate whose real instruction count is not the target's."""

    if report.instruction_delta == 0:
        return None
    message = (
        f"NI: {report.candidate_name} holds {report.candidate_rows} real "
        f"instruction(s) against the target's {report.target_rows} "
        f"({report.instruction_delta:+d}). Rows below are paired through the "
        "alignment, so the slot scores are still meaningful -- but a "
        "row-for-row scorer would have shifted every row after the divergence "
        "and reported a number for a different question."
    )
    if strict:
        raise PhaseError(
            message + " --require-ni was passed, so this candidate is not scored."
        )
    return message


def _census_lines(reports: list[PhaseReport]) -> list[str]:
    """One line per candidate: the batch reading a sweep needs."""

    labels, shared = shorten_paths([item.candidate_name for item in reports])
    width = max(len(labels[item.candidate_name]) for item in reports)
    vector_width = max(len(" ".join(item.phase_vector)) for item in reports)
    lines = [
        f"{'candidate'.ljust(width)}  {'ni':>5s} {'delta':>6s}  "
        f"{'phase'.ljust(vector_width)}  {'free':>6s} {'positional':>10s}  note"
    ]
    for item in sorted(
        reports, key=lambda report: (report.positional, report.candidate_name)
    ):
        note = "" if item.quotiented_is_bare else "COSET"
        if item.instruction_delta:
            note = f"SHIFTED {note}".strip()
        lines.append(
            f"{labels[item.candidate_name].ljust(width)}  {item.candidate_rows:5d} "
            f"{item.instruction_delta:+6d}  "
            f"{' '.join(item.phase_vector).ljust(vector_width)}  "
            f"{item.quotiented:6d} {item.positional:10d}  {note}"
        )
    lines.append("")
    if shared:
        lines.append(shared)
    lines.append(
        "free is quotiented by each slot's best-fit ring coset; positional is "
        "what the object scores as written. They agree only for a row marked "
        "with no COSET note -- rank on positional."
    )
    return lines


def phase_command(args: argparse.Namespace) -> int:
    """Report the ring-phase vector of one or more candidates."""

    cache = (
        DisassemblyCache(args.disassembly_cache, objdump=args.objdump)
        if getattr(args, "disassembly_cache", None)
        else None
    )
    try:
        ring = parse_ring(args.ring)
        if args.cosets is None:
            if len(ring) > MAX_ALL_RING:
                args.cosets = "paired"
                print(
                    f"note: {len(ring)}-register ring is too large to permute; "
                    "searching paired cosets (pass --cosets to choose)",
                    file=sys.stderr,
                )
            else:
                args.cosets = "all"
        slots = _read_slots(args)
        base_source, base_sha = _base_identity(args)
        target = _rows(args.target, args, cache=cache)
        context = _rows(args.context, args, cache=cache) if args.context else None
        baseline = _rows(args.baseline, args, cache=cache) if args.baseline else None

        def shift_of(rows: list[Instruction], name: str) -> Any:
            return build_shift_diff(
                target,
                rows,
                target_name=display_path(args.target),
                candidate_name=name,
                symbol=args.symbol,
                granularity=args.align_on,
            )

        context_shift = (
            shift_of(context, display_path(args.context))
            if context is not None
            else None
        )
        baseline_shift = (
            shift_of(baseline, display_path(args.baseline))
            if baseline is not None
            else None
        )

        reports: list[PhaseReport] = []
        notices: list[str] = []
        for candidate in args.candidates:
            rows = _rows(candidate, args, cache=cache)
            name = display_path(candidate)
            report = build_phase_report(
                target,
                rows,
                shift=shift_of(rows, name),
                slots=slots,
                ring=ring,
                coset_family=args.cosets,
                minimum_evidence=args.min_evidence,
                target_name=display_path(args.target),
                candidate_name=name,
                symbol=args.symbol,
                context=context,
                context_shift=context_shift,
                context_name=display_path(args.context) if args.context else None,
                baseline=baseline,
                baseline_shift=baseline_shift,
                baseline_name=display_path(args.baseline) if args.baseline else None,
                base_source=base_source,
                base_sha256=base_sha,
            )
            notice = _check_instruction_count(report, strict=args.require_ni)
            if notice:
                notices.append(notice)
            reports.append(report)
    except (OSError, RuntimeError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2

    rejections = [f"cache: {event}" for event in (cache.rejections if cache else [])]
    if args.json:
        if len(reports) == 1:
            payload: dict[str, Any] = reports[0].as_dict()
        else:
            payload = {
                "schema": PHASE_CENSUS_SCHEMA,
                "target": display_path(args.target),
                "candidates": [item.as_dict() for item in reports],
            }
        payload["instruction_count_notices"] = notices
        payload["cache_rejections"] = [
            event.as_dict()
            for event in (cache.events if cache else [])
            if event.status == "rejected"
        ]
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0

    if len(reports) == 1:
        lines = phase_lines(reports[0], detail=args.detail)
    else:
        lines = _census_lines(reports)
        if notices:
            lines.extend(("", *notices))
    if rejections:
        lines.extend(("", *rejections))
    emit_lines(lines, width=args.width, pager=args.pager)
    return 0


def _add_arguments(parser: argparse.ArgumentParser, *, object_inputs: bool) -> None:
    parser.add_argument(
        "--slots",
        metavar="NAME=LO..HI,...",
        help=(
            "named, inclusive target row ranges to read the phase over; they "
            "must partition the object's rows exactly, and a hole or an "
            "overlap is an error naming the rows. Default: one slot covering "
            "the whole object"
        ),
    )
    parser.add_argument(
        "--slots-from",
        metavar="FILE",
        help=(
            "read the slot table from a file, one NAME=LO..HI per line, "
            "'#' starting a comment; use this rather than a shell variable, "
            "which zsh does not word-split"
        ),
    )
    parser.add_argument(
        "--ring",
        default=",".join(DEFAULT_RING),
        metavar="REGISTERS",
        help=(
            "the scratch ring whose rotation is quotiented out "
            f"(default: {','.join(DEFAULT_RING)})"
        ),
    )
    parser.add_argument(
        "--cosets",
        choices=COSET_FAMILIES,
        default=None,
        help=(
            "which renamings count as the same allocation rotated: all "
            "permutations of the ring, or paired (identity plus disjoint-pair "
            "swaps, the physically plausible set) (default: all, falling back "
            "to paired with a notice when the ring is too large to permute)"
        ),
    )
    parser.add_argument(
        "--min-evidence",
        type=int,
        default=1,
        metavar="ROWS",
        help=(
            "rows whose match depends on the coset that a slot needs before "
            "its phase is reported as measured; below this the slot reads "
            "no-evidence rather than being labelled from one row (default: 1)"
        ),
    )
    parser.add_argument(
        "--context",
        metavar="OBJECT",
        help=(
            "score each slot at the coset this object measures, instead of at "
            "the candidate's own best fit. A small slot classified in "
            "isolation lands on whichever permutation happens to win; scored "
            "on a context that already uses the ring, its real cost shows"
        ),
    )
    parser.add_argument(
        "--baseline",
        metavar="OBJECT",
        help=(
            "also report which rows this candidate healed and which it broke "
            "against a previous candidate, rather than only the net score"
        ),
    )
    parser.add_argument(
        "--base",
        metavar="SOURCE",
        help="stamp the source file these candidates were built from, by SHA-256",
    )
    parser.add_argument(
        "--require-base",
        metavar="SHA256",
        help=(
            "refuse to score unless --base has this SHA-256 (a prefix is "
            "enough); stops a table of objects built from one base being "
            "compared with an object built from another"
        ),
    )
    parser.add_argument(
        "--require-ni",
        action="store_true",
        help=(
            "refuse to score a candidate whose real instruction count is not "
            "the target's, instead of scoring it and flagging the shift"
        ),
    )
    parser.add_argument(
        "--align-on",
        choices=ALIGNMENT_GRANULARITIES,
        default=DEFAULT_GRANULARITY,
        help=(
            "granularity the rows are paired at before scoring "
            f"(default: {DEFAULT_GRANULARITY}; see `align`)"
        ),
    )
    parser.add_argument(
        "--detail",
        action="store_true",
        help="also print where inside each slot the residual rows fall",
    )
    add_symbol_argument(
        parser,
        help_text="read only this exact symbol; --function is the same option",
    )
    if object_inputs:
        parser.add_argument(
            "--section", default=".text", help="object section (default: .text)"
        )
        parser.add_argument(
            "--objdump",
            help="GNU-compatible MIPS objdump; auto-detected when omitted",
        )
        parser.add_argument(
            "--disassembly-cache",
            metavar="DIR",
            help=(
                "reuse disassemblies from this directory across runs; entries "
                "are rebuilt unless they prove they are a complete "
                "disassembly of the object on disk"
            ),
        )
    parser.add_argument(
        "--json",
        action="store_true",
        help=(
            "emit JSON. One candidate is a `decomp-workbench-phase-v1` "
            "report; more than one is a `decomp-workbench-phase-census-v1` "
            "document holding one such report per candidate under "
            "`candidates`. Switch on `schema`"
        ),
    )
    add_explain_keys_argument(parser)
    add_terminal_arguments(parser)


_DESCRIPTION = (
    "Read a candidate's scratch-ring phase as a vector over named row slots. "
    "A float-heavy function is often not wrong but rotated: the same values "
    "in the same ring, starting at a different register, so whole regions "
    "differ in every row while being one renaming away from exact. This "
    "reports, per slot, the ring coset that would make it match, the "
    "quotiented count under that coset, and the positional count it really "
    "scores -- never the first without the second, because a bare quotiented "
    "number reads as progress an object has not made. Slots are checked to "
    "partition the row space, so no mismatch can fall in a gap, and rows are "
    "paired through the same alignment `align` reports, so an inserted "
    "instruction shifts the comparison instead of destroying it."
)


def register_phase_commands(commands: argparse._SubParsersAction[Any]) -> None:
    """Register ``phase`` and ``phase-dumps``."""

    parser = commands.add_parser(
        "phase",
        help="read the scratch-ring phase vector over named row slots",
        description=_DESCRIPTION,
        epilog=(
            "example: decomp-workbench phase target.o candidate.o "
            "--slots head=1..2038,body=2039..4200,tail=4201..4641"
        ),
    )
    parser.add_argument("target", help="reference object")
    parser.add_argument("candidates", nargs="+", help="candidate object(s)")
    _add_arguments(parser, object_inputs=True)
    parser.set_defaults(handler=phase_command, dumps=False, report_command="phase")

    dumps = commands.add_parser(
        "phase-dumps",
        help="read the ring phase from retained objdump text",
        description=_DESCRIPTION
        + " This variant reads retained `objdump -d -r` text, for a reader "
        "who has the dumps but not the objects.",
    )
    dumps.add_argument("target", help="retained target disassembly")
    dumps.add_argument("candidates", nargs="+", help="retained candidate disassembly")
    _add_arguments(dumps, object_inputs=False)
    dumps.set_defaults(
        handler=phase_command,
        dumps=True,
        objdump=None,
        section=".text",
        disassembly_cache=None,
        report_command="phase-dumps",
    )
