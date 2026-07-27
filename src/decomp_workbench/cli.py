"""Command-line interface for decomp-workbench."""

from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import cast

from . import __version__
from .campaign import render_compile_command as render_campaign_command
from .campaign import run_campaign
from .compare import compare_instructions, compare_objects
from .globalcolor import parse_globalcolor_trace
from .instrument import instrument_ugen
from .instrument_alias import instrument_uopt_alias
from .instrument_profiles import (
    SUPPORTED_PROFILES,
    instrument_uopt_profiles,
)
from .instrument_uopt import instrument_uopt_globalcolor
from .model import Comparison, CompileResult, display_path
from .objdump import parse_disassembly
from .pass_replay import ListingEdit, replay_as1
from .trace import (
    alias_trace_summary,
    parse_integer,
    parse_register,
    parse_trace,
    register_name,
    replay_fifo,
    trace_summary,
)


def add_common_compare_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--symbol", help="compare only this exact symbol")
    parser.add_argument(
        "--section", default=".text", help="object section (default: .text)"
    )
    parser.add_argument(
        "--objdump",
        help="GNU-compatible MIPS objdump; auto-detected when omitted",
    )
    parser.add_argument("--json", action="store_true", help="emit JSON")


def comparison_line(item: Comparison) -> str:
    return (
        f"words={item.word_mismatches:4d} "
        f"raw={item.raw_word_mismatches:4d} "
        f"norm={item.normalized_distance:4d} "
        f"regs={item.register_mismatches:4d} "
        f"fp={item.fp_register_mismatches:4d} "
        f"insns={item.candidate_instructions:4d} "
        f"frame={item.candidate_frame_size!s:>5s} "
        f"sha1={item.candidate_sha1} {item.candidate}"
    )


def compare_command(args: argparse.Namespace) -> int:
    try:
        comparison = compare_objects(
            args.target,
            args.candidate,
            objdump=args.objdump,
            symbol=args.symbol,
            section=args.section,
        )
    except (OSError, RuntimeError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(comparison.as_dict(), indent=2, sort_keys=True))
    else:
        print(comparison_line(comparison))
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
            for item in comparison.register_diff:
                print(f"\n[{item['index']}] target    {item['target']}")
                print(f"    candidate {item['candidate']}")
    return 1 if args.fail_on_mismatch and not comparison.exact else 0


def compare_dumps_command(args: argparse.Namespace) -> int:
    try:
        target_text = Path(args.target).read_text(encoding="utf-8")
        candidate_text = Path(args.candidate).read_text(encoding="utf-8")
    except OSError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    target = parse_disassembly(target_text, symbol=args.symbol)
    candidate = parse_disassembly(candidate_text, symbol=args.symbol)
    if not target or not candidate:
        detail = f" for symbol {args.symbol!r}" if args.symbol else ""
        print(
            "error: both files must contain GNU-style objdump instruction "
            f"lines{detail}",
            file=sys.stderr,
        )
        return 2
    comparison = compare_instructions(
        target,
        candidate,
        target_name=display_path(args.target),
        candidate_name=display_path(args.candidate),
        symbol=args.symbol,
    )
    if args.json:
        print(json.dumps(comparison.as_dict(), indent=2, sort_keys=True))
    else:
        print(comparison_line(comparison))
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
            for item in comparison.register_diff:
                print(f"\n[{item['index']}] target    {item['target']}")
                print(f"    candidate {item['candidate']}")
    return 1 if args.fail_on_mismatch and not comparison.exact else 0


def rank_command(args: argparse.Namespace) -> int:
    comparisons: list[Comparison] = []
    errors: list[dict[str, str]] = []
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
    comparisons.sort(key=lambda item: item.sort_key)
    limited = comparisons[: args.limit] if args.limit else comparisons
    if args.json:
        print(
            json.dumps(
                {
                    "results": [item.as_dict() for item in limited],
                    "errors": errors,
                },
                indent=2,
                sort_keys=True,
            )
        )
    else:
        for rank, item in enumerate(limited, 1):
            print(f"{rank:3d} {comparison_line(item)}")
        for failure in errors:
            print(
                f"ERROR {failure['candidate']}: {failure['error']}",
                file=sys.stderr,
            )
    return 0 if comparisons else 1


def render_compile_command(template: str, source: Path, output: Path) -> list[str]:
    """Render a compiler command without invoking a shell."""

    return render_campaign_command(template, source, output)


def compile_sources(
    sources: Iterable[str],
    *,
    target: str,
    template: str,
    objdump: str | None,
    symbol: str | None,
    section: str,
    keep_objects: str | None,
) -> list[CompileResult]:
    """Compile and compare source candidates."""

    results: list[CompileResult] = []
    keep_dir = Path(keep_objects) if keep_objects else None
    if keep_dir:
        keep_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="decomp-workbench-") as temp:
        temp_dir = Path(temp)
        for index, source_name in enumerate(sources):
            source = Path(source_name).resolve()
            output = temp_dir / f"{index:05d}-{source.stem}.o"
            command = render_compile_command(template, source, output)
            process = subprocess.run(
                command,
                check=False,
                capture_output=True,
                text=True,
            )
            comparison: Comparison | None = None
            kept: str | None = None
            if process.returncode == 0 and output.is_file():
                comparison = compare_objects(
                    target,
                    output,
                    objdump=objdump,
                    symbol=symbol,
                    section=section,
                )
                comparison.candidate = display_path(source)
                if keep_dir:
                    destination = keep_dir / f"{index:05d}-{source.stem}.o"
                    shutil.copy2(output, destination)
                    kept = str(destination)
            results.append(
                CompileResult(
                    source=display_path(source),
                    command=command,
                    returncode=process.returncode,
                    stdout=process.stdout,
                    stderr=process.stderr,
                    object_path=kept,
                    comparison=comparison,
                )
            )
    return results


def compile_rank_command(args: argparse.Namespace) -> int:
    try:
        results = compile_sources(
            args.sources,
            target=args.target,
            template=args.compile_command,
            objdump=args.objdump,
            symbol=args.symbol,
            section=args.section,
            keep_objects=args.keep_objects,
        )
    except (OSError, RuntimeError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    successes = [
        (item, item.comparison) for item in results if item.comparison is not None
    ]
    successes.sort(key=lambda item: item[1].sort_key)
    failures = [item for item in results if item.comparison is None]
    ordered = [item for item, _ in successes] + failures
    if args.limit:
        ordered = ordered[: args.limit]
    if args.json:
        print(
            json.dumps(
                [item.as_dict() for item in ordered],
                indent=2,
                sort_keys=True,
            )
        )
    else:
        for rank, (_, comparison) in enumerate(successes[: args.limit or None], 1):
            print(f"{rank:3d} {comparison_line(comparison)}")
        for result in failures:
            detail = result.stderr.strip().splitlines()
            message = detail[-1] if detail else f"exit {result.returncode}"
            print(f"FAIL {result.source}: {message}", file=sys.stderr)
    return 0 if successes else 1


def parse_environment(values: list[str]) -> dict[str, str]:
    """Parse explicit NAME=VALUE compiler environment entries."""

    result: dict[str, str] = {}
    for value in values:
        name, separator, content = value.partition("=")
        if (
            not separator
            or not name
            or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name)
        ):
            raise ValueError(f"invalid environment entry: {value!r}")
        result[name] = content
    return result


def campaign_command(args: argparse.Namespace) -> int:
    try:
        environment = parse_environment(args.env)
        results, duplicates = run_campaign(
            args.sources,
            target=args.target,
            template=args.compile_command,
            cache_dir=args.cache_dir,
            ledger=args.ledger,
            jobs=args.jobs,
            objdump=args.objdump,
            symbol=args.symbol,
            section=args.section,
            environment=environment,
            keep_objects=args.keep_objects,
        )
    except (OSError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    shown = results[: args.limit] if args.limit else results
    if args.json:
        print(
            json.dumps(
                {
                    "schema": "decomp-workbench-campaign-v1",
                    "unique_candidates": len(results),
                    "source_files": sum(len(items) for items in duplicates.values()),
                    "results": [item.as_dict() for item in shown],
                },
                indent=2,
                sort_keys=True,
            )
        )
    else:
        for rank, result in enumerate(shown, 1):
            if result.comparison:
                cache = "cache" if result.cached else "built"
                print(
                    f"{rank:3d} {comparison_line(result.comparison)} "
                    f"[{cache} {result.duration_seconds:.2f}s]"
                )
            else:
                detail = result.stderr.strip().splitlines()
                message = detail[-1] if detail else f"exit {result.returncode}"
                print(f"FAIL {result.source}: {message}", file=sys.stderr)
        duplicate_count = sum(len(items) - 1 for items in duplicates.values())
        if duplicate_count:
            print(f"deduplicated {duplicate_count} identical source file(s)")
        if args.ledger:
            print(f"ledger: {Path(args.ledger).resolve()}")
    return 0 if any(item.comparison for item in results) else 1


def instrument_command(args: argparse.Namespace) -> int:
    source_path = Path(args.input)
    output_path = Path(args.output)
    if source_path.resolve() == output_path.resolve() and not args.in_place:
        print(
            "error: input and output are identical; pass --in-place to confirm",
            file=sys.stderr,
        )
        return 2
    try:
        result = instrument_ugen(
            source_path.read_text(encoding="utf-8"),
            function_pattern=args.functions,
        )
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(result.source, encoding="utf-8")
    except (OSError, ValueError, re.error) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    print(
        f"instrumented {result.functions} functions and "
        f"{result.free_list_hooks} free-list hooks -> {output_path}"
    )
    return 0


def instrument_uopt_command(args: argparse.Namespace) -> int:
    source_path = Path(args.input)
    output_path = Path(args.output)
    if source_path.resolve() == output_path.resolve() and not args.in_place:
        print(
            "error: input and output are identical; pass --in-place to confirm",
            file=sys.stderr,
        )
        return 2
    try:
        result = instrument_uopt_globalcolor(
            source_path.read_text(encoding="utf-8"),
            allow_unverified_source=args.allow_unverified_source,
        )
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(result.source, encoding="utf-8")
    except (OSError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    print(
        f"instrumented {result.trace_points} globalcolor sites "
        f"using {result.profile} -> {output_path}"
    )
    return 0


def instrument_alias_command(args: argparse.Namespace) -> int:
    source_path = Path(args.input)
    output_path = Path(args.output)
    if source_path.resolve() == output_path.resolve() and not args.in_place:
        print(
            "error: input and output are identical; pass --in-place to confirm",
            file=sys.stderr,
        )
        return 2
    try:
        result = instrument_uopt_alias(
            source_path.read_text(encoding="utf-8"),
            allow_unverified_source=args.allow_unverified_source,
        )
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(result.source, encoding="utf-8")
    except (OSError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    print(
        f"instrumented {result.trace_points} alias-decision sites "
        f"using {result.profile} -> {output_path}"
    )
    return 0


def instrument_profiles_command(args: argparse.Namespace) -> int:
    source_path = Path(args.input)
    output_path = Path(args.output)
    if source_path.resolve() == output_path.resolve() and not args.in_place:
        print(
            "error: input and output are identical; pass --in-place to confirm",
            file=sys.stderr,
        )
        return 2
    try:
        result = instrument_uopt_profiles(
            source_path.read_text(encoding="utf-8"),
            args.profile,
            allow_unverified_source=args.allow_unverified_source,
        )
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(result.source, encoding="utf-8")
    except (OSError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    print(
        f"instrumented {result.trace_points} sites from "
        f"{', '.join(result.profiles)} using {result.profile} -> {output_path}"
    )
    return 0


def trace_summary_command(args: argparse.Namespace) -> int:
    try:
        events = parse_trace(Path(args.trace).read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    summary = trace_summary(events)
    if args.json:
        print(json.dumps(summary, indent=2, sort_keys=True))
    else:
        print(f"events: {summary['events']}")
        for action, count in summary["actions"].items():
            print(f"  {action:18s} {count}")
        if summary["registers"]:
            print(
                "registers: "
                + " ".join(
                    f"{name}={count}" for name, count in summary["registers"].items()
                )
            )
    return 0 if events else 1


def trace_alias_command(args: argparse.Namespace) -> int:
    try:
        events = parse_trace(Path(args.trace).read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    report = alias_trace_summary(events)
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(
            f"base-events={report['base_events']} "
            f"alias-queries={report['alias_queries']}"
        )
        for label, values in (
            ("base paths", report["base_paths"]),
            ("base types", report["base_types"]),
            ("results", report["query_results"]),
            ("left types", report["left_types"]),
            ("right types", report["right_types"]),
        ):
            if values:
                print(
                    f"{label}: "
                    + " ".join(f"{name}={count}" for name, count in values.items())
                )
        if args.show_queries:
            for event in events:
                if event.action != "alias-query":
                    continue
                left = event.fields.get("left_type", "?")
                right = event.fields.get("right_type", "?")
                result = event.fields.get("result", "?")
                register = (
                    register_name(event.register) if event.register is not None else "-"
                )
                print(
                    f"line={event.index:<5d} reg={register:>3s} "
                    f"{left:>8s} ↔ {right:<8s} {result}"
                )
    return 0 if report["events"] else 1


def parse_register_list(value: str | None) -> list[int] | None:
    if value is None:
        return None
    return [parse_register(item) for item in value.split(",") if item.strip()]


def trace_fifo_command(args: argparse.Namespace) -> int:
    try:
        events = parse_trace(Path(args.trace).read_text(encoding="utf-8"))
        initial = parse_register_list(args.initial)
        selected = parse_register_list(args.registers)
        list_address = parse_integer(args.list_address) if args.list_address else None
        if args.list_address and list_address is None:
            raise ValueError(f"invalid list address: {args.list_address!r}")
        report = replay_fifo(
            events,
            initial_queue=initial,
            registers=set(selected) if selected is not None else None,
            list_address=list_address,
        )
    except (OSError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(report.as_dict(), indent=2, sort_keys=True))
    else:
        print(
            "initial: " + " ".join(register_name(item) for item in report.initial_queue)
        )
        print(
            "allocations: "
            + " ".join(register_name(item) for item in report.allocations)
        )
        print("final: " + " ".join(register_name(item) for item in report.final_queue))
        print(
            f"logical values: "
            f"{sum(event.action == 'allocate' for event in report.logical_events)} "
            f"max-live={report.max_live}"
        )
        for violation in report.violations:
            print(f"VIOLATION {violation}", file=sys.stderr)
        if args.show_events:
            for event in report.logical_events:
                print(
                    f"{event.action:8s} v{event.value:<4d} "
                    f"{register_name(event.register):>3s} "
                    f"source={event.source_line or '-':>5} "
                    f"trace={event.trace_line}"
                )
    return 1 if args.fail_on_violation and not report.valid else 0


def trace_globalcolor_command(args: argparse.Namespace) -> int:
    try:
        report = parse_globalcolor_trace(Path(args.trace).read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    selected = report.ranked(dtype=args.dtype, limit=args.top)
    if args.json:
        print(
            json.dumps(
                {
                    "live_ranges": [item.as_dict() for item in selected],
                    "decisions": [item.as_dict() for item in report.decisions],
                    "unparsed_diagnostic_lines": (report.unparsed_diagnostic_lines),
                },
                indent=2,
                sort_keys=True,
            )
        )
    else:
        for item in selected:
            costs = sorted(item.finite_costs, key=lambda entry: entry.cost)
            best = f"r{costs[0].register}:{costs[0].cost:g}" if costs else "-"
            print(
                f"bitpos={item.bitpos:5d} dtype={item.dtype:2d} "
                f"weight={item.weight:5d} "
                f"adjsave={item.adjusted_save:11g} "
                f"total={item.total_save:13g} best={best}"
            )
        print(
            f"live-ranges={len(report.live_ranges)} "
            f"decisions={len(report.decisions)} "
            f"unparsed={len(report.unparsed_diagnostic_lines)}"
        )
    return 0 if report.live_ranges or report.decisions else 1


def parse_listing_edit(value: str, position: str) -> ListingEdit:
    pattern, separator, text = value.partition("=")
    if not separator or not pattern:
        raise ValueError(f"--insert-{position} expects REGEX=TEXT: {value!r}")
    return ListingEdit(position=position, pattern=pattern, text=text)


def replay_as1_command(args: argparse.Namespace) -> int:
    try:
        edits = [
            *(parse_listing_edit(value, "before") for value in args.insert_before),
            *(parse_listing_edit(value, "after") for value in args.insert_after),
        ]
        result = replay_as1(
            args.listing,
            args.output,
            as0_template=args.as0_command,
            as1_template=args.as1_command,
            edits=edits,
            allow_multiple=args.allow_multiple,
            keep_work=args.keep_work,
        )
    except (OSError, RuntimeError, ValueError, re.error) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(result.__dict__, indent=2, sort_keys=True))
    else:
        print(f"as0: {shlex.join(result.as0_command)}")
        print(f"as1: {shlex.join(result.as1_command)}")
        print(f"object: {result.output}")
        if result.retained_directory:
            print(f"retained: {result.retained_directory}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="decomp-workbench",
        description=(
            "MIPS object comparison, candidate campaigns, compiler traces, "
            "and pass replay"
        ),
    )
    parser.add_argument(
        "--version", action="version", version=f"%(prog)s {__version__}"
    )
    commands = parser.add_subparsers(dest="command", required=True)

    compare_parser = commands.add_parser(
        "compare",
        help="compare two MIPS objects",
        description="Compare instruction words, relocations, structure, and registers.",
    )
    compare_parser.add_argument("target", help="reference object")
    compare_parser.add_argument("candidate", help="candidate object")
    add_common_compare_arguments(compare_parser)
    compare_parser.add_argument(
        "--show-diff", action="store_true", help="show localized register differences"
    )
    compare_parser.add_argument(
        "--fail-on-mismatch",
        action="store_true",
        help="return exit 1 unless the comparison is exact",
    )
    compare_parser.set_defaults(handler=compare_command)

    dumps_parser = commands.add_parser(
        "compare-dumps",
        help="compare retained GNU objdump text without object files",
        description="Run the object comparator on redistributable objdump text.",
    )
    dumps_parser.add_argument("target", help="reference objdump text")
    dumps_parser.add_argument("candidate", help="candidate objdump text")
    dumps_parser.add_argument("--symbol", help="compare only this exact symbol")
    dumps_parser.add_argument("--json", action="store_true", help="emit JSON")
    dumps_parser.add_argument(
        "--show-diff", action="store_true", help="show localized register differences"
    )
    dumps_parser.add_argument(
        "--fail-on-mismatch",
        action="store_true",
        help="return exit 1 unless the comparison is exact",
    )
    dumps_parser.set_defaults(handler=compare_dumps_command)

    rank_parser = commands.add_parser(
        "rank",
        help="rank candidate objects",
        description="Compare prebuilt candidates and sort the usable results.",
    )
    rank_parser.add_argument("target", help="reference object")
    rank_parser.add_argument("candidates", nargs="+", help="candidate objects")
    rank_parser.add_argument(
        "--limit", type=int, default=20, help="maximum results to show"
    )
    add_common_compare_arguments(rank_parser)
    rank_parser.set_defaults(handler=rank_command)

    compile_parser = commands.add_parser(
        "compile-rank",
        help="compile and rank C source candidates",
        description="Compile candidates sequentially, then rank their objects.",
    )
    compile_parser.add_argument("target", help="reference object")
    compile_parser.add_argument("sources", nargs="+", help="candidate C files")
    compile_parser.add_argument(
        "--compile-command",
        required=True,
        help="command template containing {source} and {output}",
    )
    compile_parser.add_argument(
        "--keep-objects", help="directory in which to retain compiled objects"
    )
    compile_parser.add_argument(
        "--limit", type=int, default=20, help="maximum results to show"
    )
    add_common_compare_arguments(compile_parser)
    compile_parser.set_defaults(handler=compile_rank_command)

    campaign_parser = commands.add_parser(
        "campaign",
        help="run a parallel, cached candidate campaign",
        description="Compile, cache, rank, and record source candidates.",
    )
    campaign_parser.add_argument("target", help="reference object")
    campaign_parser.add_argument("sources", nargs="+", help="candidate C files")
    campaign_parser.add_argument(
        "--compile-command",
        required=True,
        help="command template containing {source} and {output}",
    )
    campaign_parser.add_argument(
        "--cache-dir",
        default=".decomp-workbench/cache",
        help="content-cache directory",
    )
    campaign_parser.add_argument("--ledger", help="append results to this JSONL file")
    campaign_parser.add_argument(
        "--jobs",
        type=int,
        default=max(1, min(8, os.cpu_count() or 1)),
        help="parallel compiler processes",
    )
    campaign_parser.add_argument(
        "--env",
        action="append",
        default=[],
        metavar="NAME=VALUE",
        help="compiler environment included in the cache key; repeatable",
    )
    campaign_parser.add_argument(
        "--keep-objects", help="directory in which to retain compiled objects"
    )
    campaign_parser.add_argument(
        "--limit", type=int, default=20, help="maximum results to show"
    )
    add_common_compare_arguments(campaign_parser)
    campaign_parser.set_defaults(handler=campaign_command)

    instrument_parser = commands.add_parser(
        "instrument-ugen",
        help="instrument statically recompiled ugen C",
        description="Add opt-in function and free-list traces to generated ugen C.",
    )
    instrument_parser.add_argument("input", help="pristine generated ugen.c")
    instrument_parser.add_argument("output", help="instrumented output path")
    instrument_parser.add_argument(
        "--functions",
        default=r"^f_",
        help=r"regular expression selecting generated functions (default: ^f_)",
    )
    instrument_parser.add_argument(
        "--in-place",
        action="store_true",
        help="permit input and output to be the same path",
    )
    instrument_parser.set_defaults(handler=instrument_command)

    instrument_uopt_parser = commands.add_parser(
        "instrument-uopt-globalcolor",
        help="instrument the pinned IDO 5.3 static-recomp uopt profile",
        description="Add globalcolor traces and force probes to pinned uopt C.",
    )
    instrument_uopt_parser.add_argument("input", help="pristine generated uopt.c")
    instrument_uopt_parser.add_argument("output", help="instrumented output path")
    instrument_uopt_parser.add_argument(
        "--allow-unverified-source",
        action="store_true",
        help="bypass the source hash for profile development",
    )
    instrument_uopt_parser.add_argument(
        "--in-place",
        action="store_true",
        help="permit input and output to be the same path",
    )
    instrument_uopt_parser.set_defaults(handler=instrument_uopt_command)

    instrument_alias_parser = commands.add_parser(
        "instrument-uopt-alias",
        help="trace base provenance in the pinned IDO 5.3 uopt profile",
        description="Add base-provenance and alias-query traces to pinned uopt C.",
    )
    instrument_alias_parser.add_argument("input", help="pristine generated uopt.c")
    instrument_alias_parser.add_argument("output", help="instrumented output path")
    instrument_alias_parser.add_argument(
        "--allow-unverified-source",
        action="store_true",
        help="bypass the source hash for profile development",
    )
    instrument_alias_parser.add_argument(
        "--in-place",
        action="store_true",
        help="permit input and output to be the same path",
    )
    instrument_alias_parser.set_defaults(handler=instrument_alias_command)

    instrument_profiles_parser = commands.add_parser(
        "instrument-uopt",
        help="apply compatible profiles to the pinned IDO 5.3 uopt source",
        description="Apply one or more compatible profiles to pinned uopt C.",
    )
    instrument_profiles_parser.add_argument("input", help="pristine generated uopt.c")
    instrument_profiles_parser.add_argument("output", help="instrumented output path")
    instrument_profiles_parser.add_argument(
        "--profile",
        action="append",
        choices=SUPPORTED_PROFILES,
        required=True,
        help="profile to apply; repeat for a combined source",
    )
    instrument_profiles_parser.add_argument(
        "--allow-unverified-source",
        action="store_true",
        help="bypass the source hash for profile development",
    )
    instrument_profiles_parser.add_argument(
        "--in-place",
        action="store_true",
        help="permit input and output to be the same path",
    )
    instrument_profiles_parser.set_defaults(handler=instrument_profiles_command)

    summary_parser = commands.add_parser(
        "trace-summary",
        help="summarize ugen diagnostic events",
        description="Count recognized events, actions, registers, and source lines.",
    )
    summary_parser.add_argument("trace", help="captured compiler log")
    summary_parser.add_argument("--json", action="store_true", help="emit JSON")
    summary_parser.set_defaults(handler=trace_summary_command)

    alias_parser = commands.add_parser(
        "trace-alias",
        help="summarize profiled uopt base-provenance and alias decisions",
        description="Report base paths, descriptor types, and alias outcomes.",
    )
    alias_parser.add_argument("trace", help="captured compiler log")
    alias_parser.add_argument(
        "--show-queries", action="store_true", help="print each alias query"
    )
    alias_parser.add_argument("--json", action="store_true", help="emit JSON")
    alias_parser.set_defaults(handler=trace_alias_command)

    fifo_parser = commands.add_parser(
        "trace-fifo",
        help="replay a traced register free list as a FIFO",
        description="Validate queue order and assign logical value identities.",
    )
    fifo_parser.add_argument("trace", help="captured compiler log")
    fifo_parser.add_argument(
        "--initial",
        help="comma-separated initial queue; inferred from leading appends",
    )
    fifo_parser.add_argument(
        "--registers", help="comma-separated register class to include"
    )
    fifo_parser.add_argument(
        "--list-address", help="only include appends for this list"
    )
    fifo_parser.add_argument(
        "--show-events", action="store_true", help="print the logical event schedule"
    )
    fifo_parser.add_argument("--json", action="store_true", help="emit JSON")
    fifo_parser.add_argument(
        "--fail-on-violation",
        action="store_true",
        help="return exit 1 when FIFO validation fails",
    )
    fifo_parser.set_defaults(handler=trace_fifo_command)

    color_parser = commands.add_parser(
        "trace-globalcolor",
        help="summarize uopt CSAVE/CUP and CDX globalcolor traces",
        description="Rank live ranges and report color/split decisions.",
    )
    color_parser.add_argument("trace", help="captured compiler log")
    color_parser.add_argument("--dtype", type=int, help="include only this data type")
    color_parser.add_argument(
        "--top", type=int, default=20, help="maximum live ranges to show"
    )
    color_parser.add_argument("--json", action="store_true", help="emit JSON")
    color_parser.set_defaults(handler=trace_globalcolor_command)

    replay_parser = commands.add_parser(
        "replay-as1",
        help="edit a retained ugen listing and rerun as0/as1",
        description="Apply unique listing edits and rebuild through as0 and as1.",
    )
    replay_parser.add_argument("listing", help="retained ugen assembly listing")
    replay_parser.add_argument("output", help="output object path")
    replay_parser.add_argument(
        "--as0-command",
        required=True,
        help="template containing {listing} and {binasm}",
    )
    replay_parser.add_argument(
        "--as1-command",
        required=True,
        help="template containing {binasm} and {object}",
    )
    replay_parser.add_argument(
        "--insert-before",
        action="append",
        default=[],
        metavar="REGEX=TEXT",
        help="insert text before a unique regex match; repeatable",
    )
    replay_parser.add_argument(
        "--insert-after",
        action="append",
        default=[],
        metavar="REGEX=TEXT",
        help="insert text after a unique regex match; repeatable",
    )
    replay_parser.add_argument(
        "--allow-multiple",
        action="store_true",
        help="permit an edit regex to match more than once",
    )
    replay_parser.add_argument(
        "--keep-work", help="retain the edited listing and intermediate files here"
    )
    replay_parser.add_argument("--json", action="store_true", help="emit JSON")
    replay_parser.set_defaults(handler=replay_as1_command)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    handler = cast(Callable[[argparse.Namespace], int], args.handler)
    return handler(args)


if __name__ == "__main__":
    raise SystemExit(main())
