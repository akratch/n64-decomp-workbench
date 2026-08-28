"""Object comparison and ranking command journey."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

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
    add_watch_rows_argument,
)
from .compare import (
    MIXED_ALIGNMENT_CAUTION,
    compare_instructions,
    compare_objects,
    rank_comparisons,
)
from .comparison_render import (
    alignment_caution_lines,
    comparison_acceptance,
    comparison_explanation_lines,
    comparison_line,
    comparison_payload,
    diff_site_lines,
    relocation_symbol_caution_lines,
    warning_lines,
)
from .model import Comparison, Instruction, display_path
from .objdump import (
    dump_object,
    parse_selected_disassembly,
    selection_warnings,
    symbol_selection_error,
)
from .regions import (
    RegionError,
    RegionReport,
    build_region_report,
    render_region_report,
)
from .schema import COMPARISON_CENSUS_KEYS
from .staleness_cli import (
    add_freshness_arguments,
    freshness_display,
    freshness_payload,
    guard_freshness,
)
from .terminal import Painter, add_color_argument, resolve_color
from .watch_rows import (
    WatchRow,
    WatchRowError,
    evaluate_watch_rows,
    parse_watch_rows,
    watch_row_lines,
    watch_row_payload,
    watch_signature,
)

Handler = Callable[[argparse.Namespace], int]


def add_common_compare_arguments(parser: argparse.ArgumentParser) -> None:
    add_symbol_argument(parser)
    add_explain_keys_argument(parser)
    add_color_argument(parser)
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


def add_cross_rom_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--cross-rom",
        action="store_true",
        help=(
            "accept structural cross-ROM evidence; never call it an "
            "object-exact source match"
        ),
    )


def print_comparison_explanation(item: Comparison, *, cross_rom: bool) -> None:
    for line in comparison_explanation_lines(item, cross_rom=cross_rom):
        print(line)


def print_diff_sites(item: Comparison) -> None:
    """Print every differing site; the verdict never filters evidence."""

    for line in diff_site_lines(item):
        print(line)


def _region_report(
    comparison: Comparison,
    args: argparse.Namespace,
    candidate_instructions: list[Instruction] | None,
) -> RegionReport | None:
    """Build the region attribution, or explain why it is unavailable.

    Returns ``None`` when `--by-region` was not asked for. A failure to
    attribute is raised, not swallowed: a silently absent ranking reads as
    "no regions differ", which is the opposite of the truth.
    """

    source = getattr(args, "by_region", None)
    if not source:
        return None
    if candidate_instructions is None:
        raise RegionError(
            "--by-region needs the candidate's instructions with their "
            "relocations; this input form does not carry them"
        )
    return build_region_report(
        source_path=source,
        source_text=Path(source).read_text(encoding="utf-8"),
        candidate=candidate_instructions,
        sites=comparison.diff_sites,
        instruction_delta=comparison.instruction_delta,
        true_instruction_delta=comparison.true_instruction_delta,
        expected_total=comparison.word_mismatches,
    )


def comparison_rows(item: Comparison) -> int:
    """How many positional rows a comparison covers.

    The longer of the two streams: a watched row past it belongs to neither
    object, which is a different answer from "that row matches".
    """

    return max(item.target_instructions, item.candidate_instructions)


def _watch_results(
    comparison: Comparison, rows: Sequence[WatchRow]
) -> tuple[dict[str, object], list[str]]:
    """Score the watchlist against one comparison, for JSON and terminal."""

    results = evaluate_watch_rows(
        rows,
        diff_sites=comparison.diff_sites,
        compared_rows=comparison_rows(comparison),
    )
    return watch_row_payload(results), watch_row_lines(results)


def _emit_comparison(
    comparison: Comparison,
    args: argparse.Namespace,
    *,
    predicates: Sequence[Predicate],
    show_ranges: bool,
    candidate_instructions: list[Instruction] | None = None,
) -> int:
    accepted, _ = comparison_acceptance(comparison, cross_rom=args.cross_rom)
    freshness, freshness_warnings = freshness_display(
        args, args.target, args.candidate, labels=("target", "candidate")
    )
    try:
        census = evaluate_census(predicates, comparison.as_dict())
        regions = _region_report(comparison, args, candidate_instructions)
        watched = parse_watch_rows(getattr(args, "watch_rows", None))
    except (OSError, RegionError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    watch_payload, watch_lines = (
        _watch_results(comparison, watched) if watched else ({}, [])
    )
    if args.json:
        payload = comparison_payload(
            comparison,
            cross_rom=args.cross_rom,
            census=census,
        )
        payload.update(freshness_payload(freshness))
        if regions is not None:
            payload["by_region"] = regions.as_dict()
        payload.update(watch_payload)
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        painter = Painter(resolve_color(getattr(args, "color", "never")))
        for line in freshness_warnings:
            print(line)
        # What was compared, and when each side was built. A comparison
        # states its own provenance because "0 differing words" against a
        # build that predates the edit is indistinguishable from a match.
        for line in freshness.provenance_lines():
            print(f"compared: {line}")
        for line in warning_lines(comparison.warnings):
            print(line)
        for line in alignment_caution_lines(comparison):
            print(line)
        for line in relocation_symbol_caution_lines(comparison):
            print(line)
        print(comparison_line(comparison, painter))
        for line in watch_lines:
            print(line)
        print_comparison_explanation(comparison, cross_rom=args.cross_rom)
        if show_ranges:
            print(f"register ranges: {comparison.register_mismatch_ranges or 'none'}")
            print(f"FP ranges: {comparison.fp_mismatch_ranges or 'none'}")
        if comparison.relocation_metadata_mismatches:
            print(
                "relocation metadata mismatches: "
                f"{comparison.relocation_metadata_mismatches}"
            )
        if comparison.unknown_relocations:
            print(
                "unknown relocations (not masked): "
                + ", ".join(comparison.unknown_relocations)
            )
        if args.show_diff:
            print_diff_sites(comparison)
        if regions is not None:
            limit = getattr(args, "by_region_limit", 0) or None
            print("")
            print("\n".join(render_region_report(regions, limit=limit)))
        print_census(census)
    return census_status(
        census,
        otherwise=1 if args.fail_on_mismatch and not accepted else 0,
    )


def compare_command(args: argparse.Namespace) -> int:
    candidate_instructions: list[Instruction] | None = None
    try:
        guard_freshness(
            args, args.target, args.candidate, labels=("target", "candidate")
        )
        predicates = parse_census(args.census, allowed=COMPARISON_CENSUS_KEYS)
        comparison = compare_objects(
            args.target,
            args.candidate,
            objdump=args.objdump,
            symbol=args.symbol,
            section=args.section,
        )
        if getattr(args, "by_region", None):
            # Region attribution reads the candidate's own relocations, which
            # the comparison does not carry, so the candidate is dumped again.
            _, candidate_instructions = dump_object(
                args.candidate,
                objdump=args.objdump,
                symbol=args.symbol,
                section=args.section,
            )
    except (OSError, RuntimeError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    return _emit_comparison(
        comparison,
        args,
        predicates=predicates,
        show_ranges=True,
        candidate_instructions=candidate_instructions,
    )


def compare_dumps_command(args: argparse.Namespace) -> int:
    try:
        guard_freshness(
            args, args.target, args.candidate, labels=("target", "candidate")
        )
        predicates = parse_census(args.census, allowed=COMPARISON_CENSUS_KEYS)
        target_text = Path(args.target).read_text(encoding="utf-8")
        candidate_text = Path(args.candidate).read_text(encoding="utf-8")
        target = parse_selected_disassembly(target_text, symbol=args.symbol)
        candidate = parse_selected_disassembly(candidate_text, symbol=args.symbol)
        if not target or not candidate:
            raise ValueError(
                symbol_selection_error(
                    args.symbol,
                    inputs=(
                        (display_path(args.target), target_text),
                        (display_path(args.candidate), candidate_text),
                    ),
                )
            )
        warnings = selection_warnings(
            target_text,
            candidate_text,
            symbol=args.symbol,
            target_name=display_path(args.target),
            candidate_name=display_path(args.candidate),
        )
        comparison = compare_instructions(
            target,
            candidate,
            target_name=display_path(args.target),
            candidate_name=display_path(args.candidate),
            symbol=args.symbol,
            warnings=warnings,
        )
    except (OSError, RuntimeError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    return _emit_comparison(
        comparison,
        args,
        predicates=predicates,
        show_ranges=False,
        candidate_instructions=candidate,
    )


def rank_command(args: argparse.Namespace) -> int:
    comparisons: list[Comparison] = []
    errors: list[dict[str, str]] = []
    try:
        watched = parse_watch_rows(getattr(args, "watch_rows", None))
    except WatchRowError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    for candidate in args.candidates:
        try:
            comparisons.append(
                compare_objects(
                    args.target,
                    candidate,
                    objdump=args.objdump,
                    symbol=args.symbol,
                    section=args.section,
                )
            )
        except (OSError, RuntimeError) as error:
            errors.append({"candidate": candidate, "error": str(error)})
    mixed_alignment = len({item.alignment_comparable for item in comparisons}) > 1
    comparisons, alignment_ranking_unsafe = rank_comparisons(comparisons)
    limited = comparisons[: args.limit] if args.limit else comparisons
    if args.json:
        results: list[dict[str, Any]] = []
        for item in limited:
            payload = item.as_dict()
            if watched:
                payload.update(_watch_results(item, watched)[0])
            results.append(payload)
        print(
            json.dumps(
                {
                    "results": results,
                    "errors": errors,
                    "ranked_by": (
                        "words" if alignment_ranking_unsafe else "aligned_total"
                    ),
                    "mixed_alignment": mixed_alignment,
                    "alignment_ranking_unsafe": alignment_ranking_unsafe,
                    "watch_row_set": [entry.as_dict() for entry in watched],
                },
                indent=2,
                sort_keys=True,
            )
        )
    else:
        painter = Painter(resolve_color(getattr(args, "color", "never")))
        if alignment_ranking_unsafe:
            print(MIXED_ALIGNMENT_CAUTION)
        if watched:
            # One header for the batch, then one column string per row: a
            # per-candidate legend would cost more screen than the table.
            print(
                "watch rows (. healed, X broken, ? out of range): "
                + " ".join(entry.label for entry in watched)
            )
        for rank, item in enumerate(limited, 1):
            for line in warning_lines(item.warnings):
                print(line)
            for line in alignment_caution_lines(item):
                print(line)
            for line in relocation_symbol_caution_lines(item):
                print(line)
            signature = ""
            if watched:
                signature = (
                    watch_signature(
                        evaluate_watch_rows(
                            watched,
                            diff_sites=item.diff_sites,
                            compared_rows=comparison_rows(item),
                        )
                    )
                    + " "
                )
            print(f"{rank:3d} {signature}{comparison_line(item, painter)}")
        for failure in errors:
            print(
                f"ERROR {failure['candidate']}: {failure['error']}",
                file=sys.stderr,
            )
    return 0 if comparisons else 1


def _add_by_region_arguments(parser: argparse.ArgumentParser) -> None:
    """Add `--by-region`, the most-repeated manual step in a campaign."""

    parser.add_argument(
        "--by-region",
        metavar="SRC",
        help=(
            "group the differing words by the source construct that emitted "
            "them, ranked by count, each citing SRC:line. Attribution is "
            "call-relocation anchoring: rows are bracketed between the two "
            "calls around them, never interpolated to a line, and the report "
            "states its own coverage"
        ),
    )
    parser.add_argument(
        "--by-region-limit",
        type=int,
        default=12,
        metavar="N",
        help="show only the top N regions (default: 12; 0 for all)",
    )


def register_object_commands(
    commands: argparse._SubParsersAction[Any],
    *,
    compare_handler: Handler = compare_command,
    compare_dumps_handler: Handler = compare_dumps_command,
) -> None:
    compare = commands.add_parser(
        "compare",
        help="compare two MIPS objects",
        description="Compare instruction words, relocations, structure, and registers.",
    )
    compare.add_argument("target", help="reference object")
    compare.add_argument("candidate", help="candidate object")
    add_common_compare_arguments(compare)
    add_cross_rom_argument(compare)
    compare.add_argument(
        "--show-diff",
        action="store_true",
        help="print every differing site, grouped by class",
    )
    compare.add_argument(
        "--fail-on-mismatch",
        action="store_true",
        help="return exit 1 unless exact, or structurally exact with --cross-rom",
    )
    add_freshness_arguments(compare)
    add_watch_rows_argument(compare)
    _add_by_region_arguments(compare)
    add_census_argument(compare)
    compare.set_defaults(handler=compare_handler)

    dumps = commands.add_parser(
        "compare-dumps",
        help="compare retained GNU objdump text without object files",
        description="Run the object comparator on redistributable objdump text.",
    )
    dumps.add_argument("target", help="reference objdump text")
    dumps.add_argument("candidate", help="candidate objdump text")
    add_symbol_argument(dumps)
    add_explain_keys_argument(dumps)
    add_color_argument(dumps)
    dumps.add_argument("--json", action="store_true", help="emit JSON")
    add_cross_rom_argument(dumps)
    dumps.add_argument(
        "--show-diff",
        action="store_true",
        help="print every differing site, grouped by class",
    )
    dumps.add_argument(
        "--fail-on-mismatch",
        action="store_true",
        help="return exit 1 unless exact, or structurally exact with --cross-rom",
    )
    add_freshness_arguments(dumps)
    add_watch_rows_argument(dumps)
    _add_by_region_arguments(dumps)
    add_census_argument(dumps)
    dumps.set_defaults(handler=compare_dumps_handler)


def register_rank_command(
    commands: argparse._SubParsersAction[Any],
    *,
    handler: Handler = rank_command,
) -> None:
    rank = commands.add_parser(
        "rank",
        help="rank candidate objects",
        description="Compare prebuilt candidates and sort the usable results.",
    )
    rank.add_argument("target", help="reference object")
    rank.add_argument("candidates", nargs="+", help="candidate objects")
    rank.add_argument("--limit", type=int, default=20, help="maximum results to show")
    add_common_compare_arguments(rank)
    add_watch_rows_argument(rank)
    rank.set_defaults(handler=handler)
