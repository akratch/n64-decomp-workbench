"""Command-line interface for decomp-workbench."""

from __future__ import annotations

import argparse
import json
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Iterable

from .compare import compare_objects
from .instrument import instrument_ugen
from .model import Comparison, CompileResult, display_path


def add_common_compare_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--symbol", help="disassemble only this symbol")
    parser.add_argument("--objdump", help="path to a GNU-compatible objdump")
    parser.add_argument("--json", action="store_true", help="emit JSON")


def comparison_line(item: Comparison) -> str:
    return (
        f"words={item.word_mismatches:4d} "
        f"norm={item.normalized_distance:4d} "
        f"regs={item.register_mismatches:4d} "
        f"fp={item.fp_register_mismatches:4d} "
        f"insns={item.candidate_instructions:4d} "
        f"frame={str(item.candidate_frame_size):>5s} "
        f"sha1={item.candidate_sha1} {item.candidate}"
    )


def compare_command(args: argparse.Namespace) -> int:
    comparison = compare_objects(
        args.target,
        args.candidate,
        objdump=args.objdump,
        symbol=args.symbol,
    )
    if args.json:
        print(json.dumps(comparison.as_dict(), indent=2, sort_keys=True))
    else:
        print(comparison_line(comparison))
        print(
            f"register ranges: {comparison.register_mismatch_ranges or 'none'}"
        )
        print(f"FP ranges: {comparison.fp_mismatch_ranges or 'none'}")
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
        for error in errors:
            print(
                f"ERROR {error['candidate']}: {error['error']}",
                file=sys.stderr,
            )
    return 0 if comparisons else 1


def render_compile_command(template: str, source: Path, output: Path) -> list[str]:
    """Render a compiler command without invoking a shell."""

    parts = shlex.split(template)
    if not any("{source}" in part for part in parts):
        raise ValueError("--compile-command must contain {source}")
    if not any("{output}" in part for part in parts):
        raise ValueError("--compile-command must contain {output}")
    return [
        part.replace("{source}", str(source)).replace("{output}", str(output))
        for part in parts
    ]


def compile_sources(
    sources: Iterable[str],
    *,
    target: str,
    template: str,
    objdump: str | None,
    symbol: str | None,
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
            keep_objects=args.keep_objects,
        )
    except ValueError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    successes = [item for item in results if item.comparison is not None]
    successes.sort(key=lambda item: item.comparison.sort_key)  # type: ignore[union-attr]
    failures = [item for item in results if item.comparison is None]
    ordered = successes + failures
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
        for rank, result in enumerate(successes[: args.limit or None], 1):
            assert result.comparison is not None
            print(f"{rank:3d} {comparison_line(result.comparison)}")
        for result in failures:
            detail = result.stderr.strip().splitlines()
            message = detail[-1] if detail else f"exit {result.returncode}"
            print(f"FAIL {result.source}: {message}", file=sys.stderr)
    return 0 if successes else 1


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
    except (OSError, ValueError, re.error) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    output_path.write_text(result.source, encoding="utf-8")
    print(
        f"instrumented {result.functions} functions and "
        f"{result.free_list_hooks} free-list hooks -> {output_path}"
    )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="decomp-workbench",
        description="MIPS object oracles and IDO ugen instrumentation",
    )
    parser.add_argument("--version", action="version", version="%(prog)s 0.1.0")
    commands = parser.add_subparsers(dest="command", required=True)

    compare_parser = commands.add_parser("compare", help="compare two objects")
    compare_parser.add_argument("target")
    compare_parser.add_argument("candidate")
    add_common_compare_arguments(compare_parser)
    compare_parser.add_argument("--show-diff", action="store_true")
    compare_parser.add_argument("--fail-on-mismatch", action="store_true")
    compare_parser.set_defaults(handler=compare_command)

    rank_parser = commands.add_parser("rank", help="rank candidate objects")
    rank_parser.add_argument("target")
    rank_parser.add_argument("candidates", nargs="+")
    rank_parser.add_argument("--limit", type=int, default=20)
    add_common_compare_arguments(rank_parser)
    rank_parser.set_defaults(handler=rank_command)

    compile_parser = commands.add_parser(
        "compile-rank", help="compile and rank C source candidates"
    )
    compile_parser.add_argument("target")
    compile_parser.add_argument("sources", nargs="+")
    compile_parser.add_argument("--compile-command", required=True)
    compile_parser.add_argument("--keep-objects")
    compile_parser.add_argument("--limit", type=int, default=20)
    add_common_compare_arguments(compile_parser)
    compile_parser.set_defaults(handler=compile_rank_command)

    instrument_parser = commands.add_parser(
        "instrument-ugen", help="instrument statically recompiled ugen C"
    )
    instrument_parser.add_argument("input")
    instrument_parser.add_argument("output")
    instrument_parser.add_argument("--functions", default=r"^f_")
    instrument_parser.add_argument("--in-place", action="store_true")
    instrument_parser.set_defaults(handler=instrument_command)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.handler(args)


if __name__ == "__main__":
    raise SystemExit(main())
