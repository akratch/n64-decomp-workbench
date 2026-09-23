"""Command journey for the insertion-pair reader: `object pairs` and its census."""

from __future__ import annotations

import argparse
import json
import subprocess  # nosec B404 - argv-only, never through a shell
import sys
from pathlib import Path
from typing import Any

from .cli_options import add_explain_keys_argument, add_symbol_argument
from .insertion_pairs import (
    LineTable,
    TraceProcedure,
    analyse_pairs,
    census_lines,
    census_report,
    census_rows,
    pair_lines,
    parse_line_table,
    parse_owner_trace,
    summarise,
)
from .model import Instruction, display_path
from .objdump import discover_objdump
from .row_source import load_dump_rows, load_object_rows
from .shift_align import ALIGNMENT_GRANULARITIES, DEFAULT_GRANULARITY
from .terminal import add_terminal_arguments, emit_lines

__all__ = ["pairs_census_command", "pairs_command", "register_pairs_commands"]


def _object_line_table(
    path: str,
    *,
    objdump: str | None,
    symbol: str | None,
    section: str,
    start: int,
    source: str | None,
) -> LineTable:
    """Run `objdump -d -l` on the candidate and read its line headers."""

    command = [discover_objdump(objdump), "-d", "-l", "-z", "-j", section, path]
    if symbol:
        command.append(f"--disassemble={symbol}")
    result = subprocess.run(  # nosec B603 - fixed argv, no shell
        command,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if result.returncode:
        raise RuntimeError(
            f"objdump -l failed on {display_path(path)}: {result.stderr.strip()}"
        )
    return parse_line_table(result.stdout, symbol=symbol, start=start, source=source)


def _inputs(
    target_path: str,
    candidate_path: str,
    *,
    dumps: bool,
    symbol: str | None,
    objdump: str | None,
    section: str,
    lines_path: str | None,
    source_name: str | None,
) -> tuple[list[Instruction], list[Instruction], LineTable | None]:
    if dumps:
        target = load_dump_rows(target_path, symbol=symbol)
        candidate = load_dump_rows(candidate_path, symbol=symbol)
    else:
        target = load_object_rows(
            target_path, objdump=objdump, symbol=symbol, section=section
        )
        candidate = load_object_rows(
            candidate_path, objdump=objdump, symbol=symbol, section=section
        )
    start = candidate[0].address if candidate else 0
    lines: LineTable | None
    if lines_path:
        lines = parse_line_table(
            Path(lines_path).read_text(encoding="utf-8"),
            symbol=symbol,
            start=start,
            source=source_name,
        )
    elif dumps:
        # A retained `objdump -d -l -r` dump carries its own line headers.
        lines = parse_line_table(
            Path(candidate_path).read_text(encoding="utf-8"),
            symbol=symbol,
            start=start,
            source=source_name,
        )
    else:
        lines = _object_line_table(
            candidate_path,
            objdump=objdump,
            symbol=symbol,
            section=section,
            start=start,
            source=source_name,
        )
    if lines is not None and not lines.lines:
        lines = None
    return target, candidate, lines


def _read_trace(path: str | None) -> tuple[dict[int, TraceProcedure] | None, str]:
    if not path:
        return None, "not supplied"
    procedures = parse_owner_trace(
        Path(path).read_text(encoding="utf-8", errors="replace")
    )
    if not procedures:
        return None, f"{display_path(path)} holds no DKWB-EMIT-V1 instruction records"
    return procedures, "supplied (not identity-gated: trace the scored object)"


def _read_texts(paths: list[str] | None) -> list[str]:
    return [Path(path).read_text(encoding="utf-8") for path in (paths or [])]


def _measure(
    target: str,
    candidate: str,
    *,
    dumps: bool,
    symbol: str | None,
    args: argparse.Namespace,
    source: str | None,
    trace: str | None,
    lines_path: str | None,
) -> dict[str, Any]:
    source_lines = (
        Path(source).read_text(encoding="utf-8").splitlines() if source else None
    )
    target_rows, candidate_rows, lines = _inputs(
        target,
        candidate,
        dumps=dumps,
        symbol=symbol,
        objdump=getattr(args, "objdump", None),
        section=getattr(args, "section", ".text"),
        lines_path=lines_path,
        source_name=Path(source).name if source else None,
    )
    if not target_rows or not candidate_rows:
        raise ValueError("no instruction rows to pair; check --symbol and --section")
    procedures, note = _read_trace(trace)
    return analyse_pairs(
        target_rows,
        candidate_rows,
        target_name=display_path(target),
        candidate_name=display_path(candidate),
        symbol=symbol,
        granularity=args.align_on,
        lines=lines,
        trace=procedures,
        trace_note=note,
        proc=args.proc,
        source=source_lines,
        context=_read_texts(args.context),
    )


def pairs_command(args: argparse.Namespace) -> int:
    """Pair a function's one-sided words and name what owns each one."""

    try:
        report = _measure(
            args.target,
            args.candidate,
            dumps=args.dumps,
            symbol=args.symbol,
            args=args,
            source=args.source,
            trace=args.trace,
            lines_path=args.lines,
        )
    except (OSError, RuntimeError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0
    emit_lines(pair_lines(report), width=args.width, pager=args.pager)
    return 0


def _row_path(
    row: dict[str, Any], key: str, base: Path, default: str | None
) -> str | None:
    """A row's path, relative to the ranking; a command-line default is not."""

    value = row.get(key)
    if value is None:
        return default
    path = Path(str(value))
    return str(path if path.is_absolute() else base / path)


def pairs_census_command(args: argparse.Namespace) -> int:
    """Run the reader over every small-delta row of a ranking."""

    ranking = Path(args.ranking)
    try:
        document = json.loads(ranking.read_text(encoding="utf-8"))
        rows, errors = census_rows(document, max_delta=args.max_delta)
    except (OSError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    base = ranking.parent
    results: list[dict[str, Any]] = []
    for row in rows:
        symbol = row["symbol"]
        target = _row_path(row, "target", base, args.target)
        candidate = _row_path(row, "candidate", base, args.candidate)
        if target is None or candidate is None:
            errors.append(
                {
                    "symbol": symbol,
                    "error": "no target or candidate: give the row `target` and "
                    "`candidate`, or pass --target and --candidate",
                }
            )
            continue
        try:
            report = _measure(
                target,
                candidate,
                dumps=bool(row.get("dumps", args.dumps)),
                symbol=symbol,
                args=args,
                source=_row_path(row, "source", base, None),
                trace=_row_path(row, "trace", base, None),
                lines_path=_row_path(row, "lines", base, None),
            )
        except (OSError, RuntimeError, ValueError) as error:
            errors.append({"symbol": symbol, "error": str(error)})
            continue
        if row.get("size_delta") is None and (
            report["size_delta"] == 0 or abs(report["size_delta"]) > args.max_delta
        ):
            continue
        size = row.get("size_bytes") or row.get("bytes")
        results.append(
            summarise(report, size_bytes=size if isinstance(size, int) else None)
        )
    census = census_report(
        results, errors, ranking=display_path(ranking), max_delta=args.max_delta
    )
    lines = census_lines(census)
    if args.out:
        try:
            with Path(args.out).open("x", encoding="utf-8") as handle:
                handle.write("\n".join(lines) + "\n")
        except FileExistsError:
            print(
                f"error: {display_path(args.out)} exists; the census never "
                "overwrites a report. Remove it or choose another path",
                file=sys.stderr,
            )
            return 2
        except OSError as error:
            print(f"error: {error}", file=sys.stderr)
            return 2
    if args.json:
        print(json.dumps(census, indent=2, sort_keys=True))
        return 0
    emit_lines(lines, width=args.width, pager=args.pager)
    return 0 if census["measured"] else 1


def _add_reader_arguments(
    parser: argparse.ArgumentParser, *, dumps: bool, census: bool = False
) -> None:
    if census:
        parser.set_defaults(proc=None)
    else:
        _add_function_arguments(parser)
    parser.add_argument(
        "--context",
        action="append",
        metavar="FILE",
        help="headers or context read for callee declarations (repeatable)",
    )
    parser.add_argument(
        "--align-on",
        choices=ALIGNMENT_GRANULARITIES,
        default=DEFAULT_GRANULARITY,
        help=f"what the aligner sees, as for `align` (default: {DEFAULT_GRANULARITY})",
    )
    if not dumps:
        parser.add_argument(
            "--section", default=".text", help="object section (default: .text)"
        )
        parser.add_argument(
            "--objdump", help="GNU-compatible MIPS objdump; auto-detected when omitted"
        )
    parser.add_argument("--json", action="store_true", help="emit JSON")
    add_explain_keys_argument(parser)
    add_terminal_arguments(parser)


def _add_function_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--source",
        metavar="C",
        help=(
            "the candidate's C source: names the translation unit in the line "
            "table and feeds the self-reassign-copy and unprototyped-call checks"
        ),
    )
    parser.add_argument(
        "--trace",
        metavar="LOG",
        help=(
            "a ugen trace (DKWB-EMIT-V1 records under DKWB-CALL stacks) of the "
            "scored object; names the construct that owns each word"
        ),
    )
    parser.add_argument(
        "--proc",
        type=int,
        help="the trace's procedure ordinal; matched by line when omitted",
    )


_DESCRIPTION = (
    "Pair a function's one-sided words: open a pair where the two streams stop "
    "being index-aligned and close it where they realign, subtract each "
    "pair's positional shadow from the masked count, class each one-sided "
    "word by encoding, and name its owner -- the source line from the "
    "candidate's line table, then the ugen construct from a trace when one "
    "is given -- and a label from a fixed vocabulary. The instrument for a "
    "function whose size is off, to run before any colour work."
)


def register_pairs_commands(commands: argparse._SubParsersAction[Any]) -> None:
    """Register ``pairs``, ``pairs-dumps`` and ``pairs-census``."""

    parser = commands.add_parser(
        "pairs",
        help="name the construct that owns each extra or missing word",
        description=_DESCRIPTION,
        epilog=(
            "example: decomp-workbench object pairs target.o candidate.o "
            "--symbol func --source func.c --trace ugen.log"
        ),
    )
    parser.add_argument("target", help="reference object")
    parser.add_argument("candidate", help="candidate object (read with objdump -l)")
    add_symbol_argument(parser, help_text="pair only this exact symbol")
    parser.add_argument(
        "--lines",
        metavar="DUMP",
        help="retained `objdump -d -l` text of the candidate, instead of running it",
    )
    _add_reader_arguments(parser, dumps=False)
    parser.set_defaults(handler=pairs_command, dumps=False, report_command="pairs")

    dumps = commands.add_parser(
        "pairs-dumps",
        help="the insertion-pair reader over retained objdump text",
        description=_DESCRIPTION
        + " This variant reads retained `objdump -d -r` text; a candidate dump "
        "made with `-l` carries its own line table.",
    )
    dumps.add_argument("target", help="retained target disassembly")
    dumps.add_argument("candidate", help="retained candidate disassembly")
    add_symbol_argument(dumps, help_text="pair only this exact symbol")
    dumps.add_argument(
        "--lines",
        metavar="DUMP",
        help="the candidate's `objdump -d -l` text, when the dump itself lacks it",
    )
    _add_reader_arguments(dumps, dumps=True)
    dumps.set_defaults(handler=pairs_command, dumps=True, report_command="pairs-dumps")

    census = commands.add_parser(
        "pairs-census",
        help="run the pair reader over every small-delta row of a ranking",
        description=(
            "Run the insertion-pair reader over every row of a ranking with "
            "0 < |size_delta| <= --max-delta bytes, and summarise the class by "
            "the edit each function needs (compiler flag, declaration, carrier "
            "deletion, frame cell, lifetime, reload, expression, unroll) -- "
            "never by positional words. Rows name `symbol` (or `name`), and "
            "`target`/`candidate` paths relative to the ranking, or share "
            "--target/--candidate; optional `source`, `trace`, `lines`, "
            "`dumps`. The summary carries classes and counts only."
        ),
        epilog=(
            "example: decomp-workbench object pairs-census ranking.json --out census.md"
        ),
    )
    census.add_argument(
        "ranking", help="ranking JSON: a row list or {functions: [...]}"
    )
    census.add_argument("--max-delta", type=int, default=12, metavar="BYTES")
    census.add_argument("--target", help="target object for rows that name none")
    census.add_argument("--candidate", help="candidate object for rows that name none")
    census.add_argument(
        "--dumps",
        action="store_true",
        help="read row inputs as retained objdump text",
    )
    census.add_argument(
        "--out",
        metavar="FILE",
        help="also write the Markdown summary here; refuses to overwrite",
    )
    _add_reader_arguments(census, dumps=False, census=True)
    census.set_defaults(handler=pairs_census_command, report_command="pairs-census")
