"""Command journey for the lever sweep: `sweep levers`.

Generate every catalogue lever (:mod:`.lever_sweep`) at every applicable
statement position of one function, compile each cell through the caller's own
recipe -- an argument vector with ``{source}`` and ``{output}``, never a shell
-- rank the cells by aligned residual against the target, and check from the
cell's own unforced records whether it reached the state a force priced.

Per cell: the stock compile first; a cell whose function moves more than
``--max-size-delta`` bytes from the base is dropped before scoring; a cell
whose function rows equal the base's is ``inert`` and copies the base's
numbers without a traced compile; otherwise the cell is aligned against the
target and compiled once more with tracing on and no force. The traced
function rows must equal the stock rows (the identity gate), or the cell's
oracle column reads ``gate``.

Project-specific glue -- where a function's TU lives, which flags it builds
with, how a project names its instrumented compiler -- stays in the project:
this command receives a recipe and a target, nothing more.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
import threading
from collections import Counter
from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .campaign import render_compile_command, run_compiler
from .cli_options import add_symbol_argument
from .environment import parse_environment, resolve_compiler_environment
from .lever_sweep import (
    LEVERS,
    BiasEntry,
    Cell,
    LeverSweepError,
    bias_targets,
    decision_rows,
    find_function,
    force_acceptance,
    generate_cells,
    interleave,
    oracle_label,
    oracle_status,
    oracle_targets,
    parse_bias,
    parse_forces,
)
from .model import Instruction
from .row_source import load_dump_rows, load_object_rows
from .shift_align import build_shift_diff

__all__ = [
    "LEVER_SWEEP_SCHEMA",
    "SweepConfig",
    "lever_sweep_command",
    "register_lever_sweep_command",
    "run_sweep",
]

LEVER_SWEEP_SCHEMA = "decomp-workbench-lever-sweep-v1"

#: Variables the sweep owns. A caller's ``--env`` may not set them: a stray
#: ``CDX_FORCE`` in the base environment would make every "unforced" cell forced.
TRACE_VARIABLES = (
    "CDX_LOG",
    "CDX_PROC",
    "CDX_DETAIL_WEB",
    "CDX_WEBREPORT",
    "CDX_OUT",
    "CDX_FORCE",
    "CDX_BIAS",
)


@dataclass
class SweepConfig:
    """Everything one sweep needs; built by the command or by a caller."""

    source: Path
    function: str
    target: Path
    template: str
    environment: dict[str, str]
    compile_cwd: Path
    scratch: Path
    proc: int = 0
    instrumented_template: str | None = None
    oracle: str = ""
    bias: str = ""
    levers: tuple[str, ...] = tuple(LEVERS)
    lines: set[int] = field(default_factory=set)
    webs: tuple[int, ...] = ()
    blocks: tuple[int, ...] = ()
    jobs: int = 2
    max_cells: int = 600
    max_size_delta: int = 16
    window: int = 3
    max_reads: int = 16
    own_line: bool = False
    headers: tuple[str, ...] = ()
    objdump: str | None = None
    section: str = ".text"
    timeout: float | None = 120.0
    keep: int = 5
    dry_run: bool = False


def _fingerprint(rows: Sequence[Instruction]) -> tuple[tuple[str, str, str], ...]:
    return tuple((row.word, row.assembly, repr(row.relocations)) for row in rows)


class _Runner:
    def __init__(self, config: SweepConfig) -> None:
        self.config = config
        self.target_rows = self.rows(config.target)
        if not self.target_rows:
            raise LeverSweepError(
                f"{config.target} holds no rows for {config.function}"
            )

    def rows(self, path: Path) -> list[Instruction]:
        with path.open("rb") as handle:
            magic = handle.read(4)
        if magic == b"\x7fELF":
            return load_object_rows(
                path,
                objdump=self.config.objdump,
                symbol=self.config.function,
                section=self.config.section,
            )
        return load_dump_rows(path, symbol=self.config.function)

    def compile(
        self,
        source: Path,
        output: Path,
        *,
        trace: Path | None = None,
        force: str | None = None,
        bias: str | None = None,
    ) -> str | None:
        """Compile once; ``None`` on success, else the last line of stderr."""

        config = self.config
        environment = dict(config.environment)
        template = config.template
        if trace is not None:
            template = config.instrumented_template or config.template
            environment.update(
                CDX_LOG="1",
                CDX_PROC=str(config.proc),
                CDX_DETAIL_WEB="all",
                CDX_WEBREPORT="1",
                CDX_OUT=str(trace),
            )
            if force:
                environment["CDX_FORCE"] = force
            if bias:
                environment["CDX_BIAS"] = bias
        command = render_compile_command(template, source, output)
        try:
            completed = run_compiler(
                command,
                environment=environment,
                compile_cwd=config.compile_cwd,
                timeout=config.timeout,
            )
        except (OSError, RuntimeError) as error:
            return str(error)
        if completed.returncode or not output.is_file():
            lines = completed.stderr.strip().splitlines()
            return (
                lines[-1] if lines else f"compile failed (exit {completed.returncode})"
            )
        if trace is not None and not trace.is_file():
            return (
                "the traced compile wrote no log to CDX_OUT; the instrumented command "
                "must be the instrumented uopt"
            )
        return None

    def score(self, rows: Sequence[Instruction]) -> dict[str, int]:
        diff = build_shift_diff(self.target_rows, rows, symbol=self.config.function)
        return {
            "residual": diff.rows_away,
            "edit_distance": diff.edit_distance,
            "paired_mismatches": diff.paired_mismatches,
            "positional": diff.positional_mismatches,
            "delta": 4 * (diff.candidate_rows - diff.target_rows),
        }


def _measure(
    runner: _Runner,
    index: int,
    cell: Cell,
    base: dict[str, Any],
    targets: list[dict[str, Any]],
    scratch: Path,
    lock: threading.Lock,
    progress: list[int],
) -> dict[str, Any]:
    config = runner.config
    directory = scratch / f"cell{index:04d}"
    directory.mkdir(parents=True, exist_ok=True)
    source = directory / ("candidate" + config.source.suffix)
    source.write_text(cell.text, encoding="utf-8")
    row: dict[str, Any] = {"index": index, **cell.as_dict()}
    try:
        output = directory / "stock.o"
        error = runner.compile(source, output)
        if error:
            row["error"] = error
            return row
        try:
            rows = runner.rows(output)
        except (OSError, RuntimeError, ValueError) as failure:
            row["error"] = f"cannot read the function: {failure}"
            return row
        size = 4 * len(rows)
        if abs(size - base["size"]) > config.max_size_delta:
            row["skipped"] = f"size moved {size - base['size']:+d}"
            return row
        fingerprint = _fingerprint(rows)
        row["equals_forced"] = fingerprint == base["forced_fingerprint"]
        if fingerprint == base["fingerprint"]:
            row.update({key: base[key] for key in ("score", "oracle", "oracle_detail")})
            row["inert"] = True
            return row
        row["score"] = runner.score(rows)
        trace = directory / "allocator.log"
        traced = directory / "traced.o"
        error = runner.compile(source, traced, trace=trace)
        if error:
            row["oracle"] = "err"
            row["oracle_error"] = error
        elif _fingerprint(runner.rows(traced)) != fingerprint:
            row["oracle"] = "gate"
        else:
            decisions, _ = decision_rows(
                trace.read_text(encoding="utf-8", errors="replace"), config.proc
            )
            hits, detail = oracle_status(decisions, targets)
            row["oracle"] = oracle_label(
                hits, len(targets), sum(bool(item["ambiguous"]) for item in detail)
            )
            row["oracle_detail"] = detail
        return row
    finally:
        for path in directory.iterdir():
            if path.name != source.name:
                path.unlink(missing_ok=True)
        with lock:
            progress[0] += 1


def _rank_key(row: dict[str, Any]) -> tuple[Any, ...]:
    if "score" not in row:
        return (1, 0, 0, 0, 0)
    score = row["score"]
    exact = score["residual"] == 0 and score["delta"] == 0
    return (
        0,
        not exact,
        score["residual"],
        row.get("oracle") != "yes",
        abs(score["delta"]),
    )


def _jsonable(value: Any) -> Any:
    if isinstance(value, set):
        return sorted(value)
    if isinstance(value, dict):
        return {key: _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    return value


def run_sweep(config: SweepConfig) -> dict[str, Any]:
    """Run one sweep and return the ``decomp-workbench-lever-sweep-v1`` report."""

    forces = parse_forces(config.oracle)
    bias: list[BiasEntry] = parse_bias(config.bias)
    if not forces and not bias:
        raise LeverSweepError(
            "give --oracle and/or --bias: the sweep needs a priced state"
        )
    unknown = [name for name in config.levers if name not in LEVERS]
    if unknown:
        raise LeverSweepError(
            f"unknown lever(s) {', '.join(unknown)}; known: {', '.join(LEVERS)}"
        )
    text = config.source.read_text(encoding="utf-8")
    function = find_function(text, config.function)
    runner = _Runner(config)
    scratch = config.scratch
    scratch.mkdir(parents=True, exist_ok=True)
    base_dir = scratch / "base"
    base_dir.mkdir(exist_ok=True)
    base_source = base_dir / ("candidate" + config.source.suffix)
    base_source.write_text(text, encoding="utf-8")
    force_text = ",".join(str(item) for item in forces) or None
    bias_text = ",".join(str(item) for item in bias) or None
    error = runner.compile(base_source, base_dir / "stock.o")
    if error:
        raise LeverSweepError(f"the base failed to compile: {error}")
    error = runner.compile(
        base_source, base_dir / "unforced.o", trace=base_dir / "unforced.log"
    )
    if error:
        raise LeverSweepError(f"the traced base failed to compile: {error}")
    error = runner.compile(
        base_source,
        base_dir / "forced.o",
        trace=base_dir / "forced.log",
        force=force_text,
        bias=bias_text,
    )
    if error:
        raise LeverSweepError(f"the forced base failed to compile: {error}")
    base_rows = runner.rows(base_dir / "stock.o")
    if _fingerprint(runner.rows(base_dir / "unforced.o")) != _fingerprint(base_rows):
        raise LeverSweepError(
            "IDENTITY GATE FAILED: the traced base's function differs from the stock "
            "compile, so no record it prints is evidence about the stock object"
        )
    forced_log = (base_dir / "forced.log").read_text(encoding="utf-8", errors="replace")
    if forces:
        refused = force_acceptance(forced_log, config.proc, forces)
        if refused:
            raise LeverSweepError(f"the oracle was not accepted on the base: {refused}")
    forced_rows, block_lines = decision_rows(forced_log, config.proc)
    targets = oracle_targets(forced_rows, forces) if forces else []
    unforced_rows, _ = decision_rows(
        (base_dir / "unforced.log").read_text(encoding="utf-8", errors="replace"),
        config.proc,
    )
    if bias:
        targets += bias_targets(unforced_rows, forced_rows, bias)
    base_hits, base_detail = oracle_status(unforced_rows, targets)
    forced_function_rows = runner.rows(base_dir / "forced.o")
    base: dict[str, Any] = {
        "size": 4 * len(base_rows),
        "fingerprint": _fingerprint(base_rows),
        "forced_fingerprint": _fingerprint(forced_function_rows),
        "score": runner.score(base_rows),
        "oracle": oracle_label(
            base_hits,
            len(targets),
            sum(bool(item["ambiguous"]) for item in base_detail),
        ),
        "oracle_detail": base_detail,
    }
    forced_score = runner.score(forced_function_rows)

    lines = set(config.lines)
    for web in config.webs:
        matched = [row for row in forced_rows if row["web"] == web]
        if not matched:
            raise LeverSweepError(
                f"--web {web}: no decision for that web in proc {config.proc}"
            )
        for row in matched:
            lines.update(row["lines"])
    for block in config.blocks:
        if block not in block_lines:
            raise LeverSweepError(
                f"--block {block}: no such block in proc {config.proc}"
            )
        lines.update(block_lines[block])
    cells = generate_cells(
        function,
        config.levers,
        lines or None,
        own_line=config.own_line,
        window=config.window,
        max_reads=config.max_reads,
        headers=config.headers,
    )
    kept = interleave(cells, config.max_cells)
    report: dict[str, Any] = {
        "schema": LEVER_SWEEP_SCHEMA,
        "function": config.function,
        "source": str(config.source),
        "target": str(config.target),
        "proc": config.proc,
        "oracle": [str(item) for item in forces] + [f"bias {item}" for item in bias],
        "targets": _jsonable(targets),
        "base": {key: value for key, value in base.items() if "fingerprint" not in key},
        "forced": {"score": forced_score},
        "generated": len(cells),
        "generated_by_lever": dict(Counter(cell.lever for cell in cells)),
        "measured": len(kept),
        "restricted_lines": sorted(lines),
        "scratch": str(scratch),
        "cells": [],
    }
    if config.dry_run:
        report["cells"] = [
            {"index": index, **cell.as_dict()} for index, cell in enumerate(kept)
        ]
        return report
    lock = threading.Lock()
    progress = [0]
    with ThreadPoolExecutor(max_workers=max(1, config.jobs)) as pool:
        results = list(
            pool.map(
                lambda pair: _measure(
                    runner, pair[0], pair[1], base, targets, scratch, lock, progress
                ),
                enumerate(kept),
            )
        )
    results.sort(key=_rank_key)
    best_dir = scratch / "best"
    best_dir.mkdir(exist_ok=True)
    scored = [row for row in results if "score" in row and not row.get("inert")]
    for row in scored[: config.keep]:
        cell_source = (
            scratch / f"cell{row['index']:04d}" / ("candidate" + config.source.suffix)
        )
        if cell_source.is_file():
            kept_path = best_dir / f"cell{row['index']:04d}{config.source.suffix}"
            shutil.copyfile(cell_source, kept_path)
            row["kept_source"] = str(kept_path)
    for row in results:
        shutil.rmtree(scratch / f"cell{row['index']:04d}", ignore_errors=True)
    report["cells"] = _jsonable(results)
    report["summary"] = {
        "scored": sum("score" in row for row in results),
        "inert": sum(bool(row.get("inert")) for row in results),
        "skipped": sum("skipped" in row for row in results),
        "errors": sum("error" in row for row in results),
        "oracle_yes": sum(row.get("oracle") == "yes" for row in scored),
        "ambiguous": sum(row.get("oracle") == "ambiguous" for row in scored),
        "exact": sum(
            row["score"]["residual"] == 0 and row["score"]["delta"] == 0
            for row in scored
        ),
        "best": scored[0] if scored else None,
    }
    return report


def render_sweep(report: dict[str, Any], *, top: int = 25) -> list[str]:
    base = report["base"]
    forced = report["forced"]["score"]
    oracle = ", ".join(report["oracle"])
    lines = [
        f"{report['function']} proc {report['proc']}: base residual "
        f"{base['score']['residual']} at {base['score']['delta']:+d} bytes; "
        f"oracle {oracle} accepted, forced residual {forced['residual']} at "
        f"{forced['delta']:+d}; base oracle state {base['oracle']}",
    ]
    for target in report["targets"]:
        if target["want"] == "order":
            lines.append(f"  oracle {target['spec']} (p1 decision order)")
            continue
        for row in target["rows"]:
            span = f"{min(row['lines'])}-{max(row['lines'])}" if row["lines"] else "-"
            lines.append(
                f"  oracle {target['spec']}: {row['decision']} row, expr "
                f"{row['expr']} kind {row['kind']}, {len(row['lines'])} lines in "
                f"{span}, forced colour {row['colour']}"
            )
    by_lever = ", ".join(
        f"{name} {count}" for name, count in report["generated_by_lever"].items()
    )
    restricted = report["restricted_lines"]
    lines.append(
        f"cells: {report['generated']} generated ({by_lever or 'none'}); "
        f"{report['measured']} measured"
        + (f"; positions restricted to {len(restricted)} lines" if restricted else "")
    )
    summary = report.get("summary")
    if summary is None:
        return lines
    lines.append(
        f"measured: {summary['scored']} scored ({summary['inert']} inert), "
        f"{summary['skipped']} size-skipped, {summary['errors']} compile errors; "
        f"oracle reproduced {summary['oracle_yes']}, ambiguous "
        f"{summary['ambiguous']}, exact {summary['exact']}"
    )
    lines.append(
        f"{'cell':>5} {'lever':<14} {'line':>5} {'resid':>5} {'delta':>6} "
        f"{'pos':>5} {'oracle':>9} {'sem':>5}  edit"
    )
    shown = [row for row in report["cells"] if "score" in row and not row.get("inert")]
    for row in shown[:top]:
        score = row["score"]
        tag = str(row.get("oracle", "-")) + ("=F" if row.get("equals_forced") else "")
        lines.append(
            f"{row['index']:>5} {row['lever']:<14} {row['line']:>5} "
            f"{score['residual']:>5} {score['delta']:>+6} {score['positional']:>5} "
            f"{tag:>9} {row['semantics']:>5}  {row['edit'][:70]}"
        )
    for row in report["cells"]:
        if row.get("oracle") != "ambiguous":
            continue
        for item in row.get("oracle_detail", []):
            if item.get("ambiguous"):
                candidates = ", ".join(item["candidates"])
                lines.append(
                    f"  cell {row['index']} ambiguous for {item['spec']}: {candidates}"
                )
    best = summary["best"]
    if best:
        lines.append(
            f"best: cell {best['index']} {best['lever']} L{best['line']} "
            f"`{best['edit'][:40]}` residual {best['score']['residual']} at "
            f"{best['score']['delta']:+d}, oracle {best.get('oracle')}"
        )
    else:
        lines.append("best: no scored cell")
    lines.append(f"best cells' sources: {Path(report['scratch']) / 'best'}")
    return lines


def _lines(value: str) -> set[int]:
    low, _, high = value.partition("-")
    try:
        first, last = int(low), int(high or low)
    except ValueError:
        raise argparse.ArgumentTypeError(
            f"{value!r} is not a line span LO-HI"
        ) from None
    return set(range(first, last + 1))


def lever_sweep_command(args: argparse.Namespace) -> int:
    if not args.symbol:
        print("error: lever-sweep needs --function NAME", file=sys.stderr)
        return 2
    try:
        environment = resolve_compiler_environment(
            parse_environment(args.env), args.inherit_env
        )
        owned = [name for name in TRACE_VARIABLES if name in environment]
        if owned:
            raise ValueError(
                f"--env may not set {', '.join(owned)}: the sweep sets tracing, "
                "forces and bias itself, and a stray force would make every "
                "unforced cell forced"
            )
        headers = tuple(
            Path(path).read_text(encoding="utf-8", errors="replace")
            for path in args.header
        )
        scratch = (
            Path(args.scratch).expanduser().resolve()
            if args.scratch
            else Path(tempfile.mkdtemp(prefix="dkwb-lever-sweep-"))
        )
        config = SweepConfig(
            source=Path(args.source).expanduser().resolve(),
            function=args.symbol,
            target=Path(args.target).expanduser().resolve(),
            template=args.compile_command,
            instrumented_template=args.instrumented_command,
            environment=environment,
            compile_cwd=(
                Path(args.compile_cwd).expanduser().resolve()
                if args.compile_cwd
                else Path.cwd().resolve()
            ),
            scratch=scratch,
            proc=args.proc,
            oracle=args.oracle,
            bias=args.bias,
            levers=tuple(
                item.strip() for item in args.levers.split(",") if item.strip()
            ),
            lines=args.lines or set(),
            webs=tuple(args.web),
            blocks=tuple(args.block),
            jobs=args.jobs,
            max_cells=args.max_cells,
            max_size_delta=args.max_size_delta,
            window=args.window,
            max_reads=args.max_reads,
            own_line=args.own_line,
            headers=headers,
            objdump=args.objdump,
            section=args.section,
            timeout=args.timeout,
            keep=args.keep,
            dry_run=args.dry_run,
        )
        report = run_sweep(config)
    except (OSError, RuntimeError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True, default=str))
    else:
        print("\n".join(render_sweep(report, top=args.top)))
    if args.dry_run:
        return 0
    summary = report["summary"]
    return 0 if summary["exact"] or summary["oracle_yes"] else 1


def register_lever_sweep_command(commands: argparse._SubParsersAction[Any]) -> None:
    """Register ``lever-sweep`` behind the ``sweep levers`` spelling."""

    parser = commands.add_parser(
        "lever-sweep",
        help="search zero-emission source levers for a force-priced allocator state",
        description=(
            "Apply every catalogue lever (assigned dead read, |= 0 keep-alive, no-op "
            "narrowing redefinition, narrower local type, scaled subscript, masked "
            "dead local, empty if (v) {} boundary, global store-then-reread, def "
            "between loops, local split/merge, statement reorder, loop moves) at "
            "each applicable statement position of one function; compile each cell "
            "with --compile-command; rank by aligned residual against --target; and "
            "check from each cell's unforced CDX records whether it reached the "
            "state --oracle (a CDX_FORCE spec) or --bias (a CDX_BIAS spec) priced. "
            "Exit 0 when a cell is exact or reproduces the oracle, 1 when none does, "
            "2 on an error."
        ),
        epilog=(
            "example: decomp-workbench sweep levers func.c --function func --target "
            "target.o --compile-command 'cc -c {source} -o {output}' --proc 0 "
            "--oracle p1:w12=c15"
        ),
    )
    parser.add_argument("source", help="the C translation unit holding the function")
    add_symbol_argument(parser, help_text="the function to edit and score")
    parser.add_argument(
        "--target", required=True, help="target object, or retained objdump text"
    )
    parser.add_argument(
        "--compile-command",
        required=True,
        help=(
            "compiler argument vector with {source} and {output}; never run "
            "through a shell"
        ),
    )
    parser.add_argument(
        "--instrumented-command",
        help=(
            "argument vector for the traced compiles (default: --compile-command, "
            "for an instrumented compiler that is byte-identical to stock with "
            "tracing off)"
        ),
    )
    parser.add_argument(
        "--proc", type=int, default=0, help="globalcolor procedure ordinal"
    )
    parser.add_argument(
        "--oracle",
        default="",
        metavar="p1:wN=cK[,...]",
        help="CDX_FORCE spec to reproduce",
    )
    parser.add_argument(
        "--bias",
        default="",
        metavar="N=DELTA[,...]",
        help="CDX_BIAS spec whose p1 decision order is the state to reproduce",
    )
    parser.add_argument(
        "--levers",
        default=",".join(LEVERS),
        help="comma list (default all): " + ", ".join(LEVERS),
    )
    parser.add_argument(
        "--lines",
        type=_lines,
        metavar="LO-HI",
        help="positions on these source lines only",
    )
    parser.add_argument(
        "--web",
        type=int,
        action="append",
        default=[],
        metavar="N",
        help="positions on this forced web's lines",
    )
    parser.add_argument(
        "--block",
        type=int,
        action="append",
        default=[],
        metavar="BB",
        help="positions on this block's lines",
    )
    parser.add_argument(
        "--header",
        action="append",
        default=[],
        metavar="FILE",
        help="C header read for struct field types",
    )
    parser.add_argument("--jobs", type=int, default=2)
    parser.add_argument(
        "--max-cells",
        type=int,
        default=600,
        help="measure at most this many (round-robin per lever)",
    )
    parser.add_argument(
        "--max-size-delta",
        type=int,
        default=16,
        help="drop a cell whose function moves more bytes than this",
    )
    parser.add_argument(
        "--window",
        type=int,
        default=3,
        help="statements either side a dead read is taken from",
    )
    parser.add_argument("--max-reads", type=int, default=16)
    parser.add_argument(
        "--own-line",
        action="store_true",
        help="put inserted statements on their own line",
    )
    parser.add_argument("--objdump", help="MIPS objdump for ELF inputs")
    parser.add_argument("--section", default=".text")
    parser.add_argument("--env", action="append", default=[], metavar="NAME=VALUE")
    parser.add_argument(
        "--inherit-env",
        action="append",
        default=[],
        metavar="NAME",
        help="copy this host variable into the otherwise sealed compiler environment",
    )
    parser.add_argument(
        "--compile-cwd", help="working directory for compiler processes"
    )
    parser.add_argument(
        "--timeout", type=float, default=120.0, help="per-compile timeout in seconds"
    )
    parser.add_argument(
        "--scratch", help="work directory (default: a fresh temporary directory)"
    )
    parser.add_argument(
        "--keep", type=int, default=5, help="keep this many best cells' sources"
    )
    parser.add_argument("--top", type=int, default=25, help="table rows to print")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="compile the base, generate and count cells only",
    )
    parser.add_argument("--json", action="store_true", help="emit JSON")
    parser.set_defaults(handler=lever_sweep_command, report_command="lever-sweep")
