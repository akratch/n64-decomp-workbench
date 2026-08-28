"""Orchestration for `permute-sweep` and `permute-doctor`.

`permute.py` holds the parsers and the policy; this module is the part that
actually starts processes: import one function into a scratch whose recipe
matches the real build, run decomp-permuter under a wall-clock cap, and
record what came back. Nothing here interprets a result, and nothing here
promotes one: a scratch score of zero is a candidate, and proving it on the
authoritative build belongs to the project that owns that build.
"""

from __future__ import annotations

import concurrent.futures
import json
import shutil
import subprocess  # nosec B404 - argv-only, never through a shell
import sys
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from .permute import (
    DOCTOR_SCHEMA,
    BuildRecipe,
    QueueItem,
    Runner,
    SweepResult,
    append_compile_steps,
    best_output,
    object_target,
    output_fraction,
    parse_base_score,
    permuter_argv,
    recipe_report,
    recover_recipe,
    render_settings,
    retarget_labels,
    retarget_objcopy,
    should_extend,
    wait_for_headroom,
)
from .project_config import PermuterOptions

Reporter = Callable[[str], None]


class PermuterError(RuntimeError):
    """A scratch could not be prepared, or a tool is missing."""


@dataclass(frozen=True)
class SweepPlan:
    """One resolved sweep: where it runs, for how long, under what limits."""

    root: Path
    options: PermuterOptions
    output_dir: Path
    minutes: int
    extend_minutes: int
    threads: int
    jobs: int
    load_threshold: float
    extra: tuple[str, ...] = ()

    @property
    def python(self) -> str:
        return self.options.python or sys.executable

    def tool(self, name: str) -> Path:
        directory = self.options.permuter_dir
        if directory is None:
            raise PermuterError(
                "permuter.permuter_dir is not configured: set it in "
                ".decomp-workbench.toml or pass --permuter-dir"
            )
        tool = directory / name
        if not tool.is_file():
            raise PermuterError(f"decomp-permuter's {name} is not at {tool}")
        return tool


def resolve_plan(
    root: Path,
    options: PermuterOptions,
    *,
    permuter_dir: str | None = None,
    output_dir: str | None = None,
    minutes: int | None = None,
    extend_minutes: int = 0,
    threads: int | None = None,
    jobs: int | None = None,
    load_threshold: float | None = None,
    make: str | None = None,
    extra: Sequence[str] = (),
    cpu_count: int = 4,
) -> SweepPlan:
    """Apply command-line overrides over the project's configured defaults."""

    if permuter_dir is not None:
        options = replace(options, permuter_dir=Path(permuter_dir).expanduser())
    if make is not None:
        options = replace(options, make=make)
    resolved_jobs = jobs or options.jobs
    resolved_threads = threads or options.threads
    if resolved_threads is None:
        # Leave two cores for the rest of the machine, then split what is
        # left across the concurrent functions rather than over-subscribing
        # every one of them to the whole box.
        resolved_threads = max(1, max(cpu_count - 2, 1) // max(resolved_jobs, 1))
    directory = (
        Path(output_dir).expanduser()
        if output_dir is not None
        else options.output_dir or root / ".decomp-workbench" / "permute"
    )
    return SweepPlan(
        root=root,
        options=options,
        output_dir=directory if directory.is_absolute() else root / directory,
        minutes=minutes or options.minutes,
        extend_minutes=max(0, extend_minutes),
        threads=max(1, resolved_threads),
        jobs=max(1, resolved_jobs),
        load_threshold=(
            options.load_threshold if load_threshold is None else load_threshold
        ),
        extra=tuple(extra),
    )


# ---------------------------------------------------------------------------
# Scratch preparation
# ---------------------------------------------------------------------------


def prepare_target_asm(root: Path, item: QueueItem, out_dir: Path) -> Path:
    """Copy the target assembly beside the scratch, renaming its label if asked.

    The rename exists because a project's extracted assembly may name a
    function by the address it was disassembled from while the C source uses
    the name a human gave it. decomp-permuter's importer looks for the
    assembly's name in the C, so without the rename the import fails on a
    naming convention rather than on anything real. The project's own
    extracted assembly is never modified.
    """

    if item.asm is None:
        raise PermuterError(
            f"{item.function}: the queue entry has no 'asm' target; "
            "decomp-permuter needs the function's target assembly"
        )
    source = Path(item.asm)
    if not source.is_absolute():
        source = root / source
    if not source.is_file():
        raise PermuterError(f"{item.function}: target assembly not found: {source}")
    text = source.read_text(encoding="utf-8", errors="replace")
    if item.asm_symbol:
        text = retarget_labels(text, old=item.asm_symbol, new=item.function)
    target = out_dir / "target.s"
    target.write_text(text, encoding="utf-8")
    return target


def import_scratch(
    plan: SweepPlan,
    item: QueueItem,
    out_dir: Path,
    settings: Path,
    target_asm: Path,
    *,
    runner: Runner = subprocess.run,
) -> Path:
    """Run decomp-permuter's `import.py`, then take ownership of its output."""

    source = Path(item.source)
    if not source.is_absolute():
        source = plan.root / source
    imported = plan.root / "nonmatchings" / item.function
    if imported.exists():
        shutil.rmtree(imported)
    completed = runner(
        [
            plan.python,
            str(plan.tool("import.py")),
            str(source),
            str(target_asm),
            "--settings",
            str(settings),
        ],
        cwd=str(plan.root),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        check=False,
    )
    (out_dir / "import.log").write_text(completed.stdout or "", encoding="utf-8")
    if completed.returncode != 0 or not imported.is_dir():
        raise PermuterError(
            f"{item.function}: import.py failed; see {out_dir / 'import.log'}"
        )
    scratch = out_dir / "scratch"
    if scratch.exists():
        shutil.rmtree(scratch)
    shutil.move(str(imported), str(scratch))
    return scratch


def prepare_scratch(
    plan: SweepPlan,
    item: QueueItem,
    *,
    runner: Runner = subprocess.run,
) -> tuple[Path, Path, BuildRecipe, tuple[str, ...]]:
    """Build one function's scratch from the project's *real* recipe.

    Returns the output directory, the scratch, the recovered recipe, and the
    post-compile steps that were replicated into `compile.sh`.
    """

    options = plan.options
    if not options.compiler_command:
        raise PermuterError(
            "permuter.compiler_command is not configured: the scratch has no "
            "base compile line to attach the recovered codegen flags to"
        )
    out_dir = plan.output_dir / item.function
    out_dir.mkdir(parents=True, exist_ok=True)
    recipe = recover_recipe(
        plan.root,
        item,
        make=options.make,
        object_template=options.object_template,
        compiler=options.compiler_marker,
        fallback_flags=options.fallback_flags,
        skip_postprocess=options.skip_postprocess,
        runner=runner,
    )
    settings = out_dir / "permuter_settings.toml"
    settings.write_text(
        render_settings(
            compiler_command=options.compiler_command,
            assembler_command=options.assembler_command or "",
            flags=recipe.flags,
            compiler_type=options.compiler_type,
            preserve_macros=options.preserve_macros,
            decompme_compiler=options.decompme_compiler,
        ),
        encoding="utf-8",
    )
    target_asm = prepare_target_asm(plan.root, item, out_dir)
    scratch = import_scratch(plan, item, out_dir, settings, target_asm, runner=runner)
    obj = item.object or object_target(options.object_template, item.source)
    steps = retarget_objcopy(recipe.objcopy_steps, obj)
    append_compile_steps(scratch / "compile.sh", steps)
    (out_dir / "recipe.txt").write_text(recipe_report(recipe, steps), encoding="utf-8")
    return out_dir, scratch, recipe, steps


# ---------------------------------------------------------------------------
# Running
# ---------------------------------------------------------------------------


def run_permuter(
    plan: SweepPlan,
    scratch: Path,
    out_dir: Path,
    *,
    minutes: int,
    log_name: str = "permuter.log",
    runner: Runner = subprocess.run,
    clock: Callable[[], float] = time.monotonic,
) -> tuple[int | None, float]:
    """Run one bounded search and return its base score and elapsed seconds."""

    log_path = out_dir / log_name
    argv = permuter_argv(
        python=plan.python,
        permuter=plan.tool("permuter.py"),
        scratch=scratch,
        threads=plan.threads,
        extra=plan.extra,
        nice=plan.options.nice,
    )
    started = clock()
    with log_path.open("w", encoding="utf-8") as log:
        try:
            runner(
                argv,
                cwd=str(plan.root),
                stdout=log,
                stderr=subprocess.STDOUT,
                timeout=minutes * 60,
                check=False,
            )
        except subprocess.TimeoutExpired:
            pass
    elapsed = clock() - started
    text = log_path.read_text(encoding="utf-8", errors="replace")
    return parse_base_score(text), elapsed


def _best_age(best_dir: Path | None, now: Callable[[], float]) -> float | None:
    """How long ago the best output directory was written, in seconds."""

    if best_dir is None:
        return None
    try:
        return now() - best_dir.stat().st_mtime
    except OSError:  # pragma: no cover - stat of a live directory
        return None


def search_function(
    plan: SweepPlan,
    item: QueueItem,
    *,
    runner: Runner = subprocess.run,
    clock: Callable[[], float] = time.monotonic,
    now: Callable[[], float] = time.time,
    report: Reporter | None = None,
) -> SweepResult:
    """Prepare, search and record one function. Never raises into the batch."""

    result = SweepResult(function=item.function, source=item.source)
    started = clock()
    try:
        out_dir, scratch, recipe, steps = prepare_scratch(plan, item, runner=runner)
        result.flags = " ".join(recipe.flags) or None
        result.flags_recovered = recipe.from_dry_run
        result.replicated_objcopy = len(steps)
        result.skipped_postprocess = len(recipe.skipped_postprocess)
        result.warnings = list(recipe.warnings)
        for warning in recipe.warnings:
            if report is not None:
                report(f"WARNING [{item.function}] {warning}")
        wait_for_headroom(
            plan.load_threshold,
            label=f"before permuting {item.function}",
            report=report,
        )
        base_score, elapsed = run_permuter(
            plan, scratch, out_dir, minutes=plan.minutes, runner=runner, clock=clock
        )
        result.base_score = base_score
        result.ok = True
        result.window_seconds = plan.minutes * 60.0
        result.hit_cap = elapsed >= result.window_seconds * 0.95
        best_dir, best_score = best_output(scratch)
        age = _best_age(best_dir, now)
        result.best_output_mtime_fraction = output_fraction(
            elapsed=elapsed, best_age=age
        )
        if should_extend(
            elapsed=elapsed,
            minutes=plan.minutes,
            best_score=best_score,
            best_age=age,
            extend_minutes=plan.extend_minutes,
        ):
            assert best_dir is not None
            result.extended = True
            shutil.copy(best_dir / "source.c", scratch / "base.c")
            wait_for_headroom(
                plan.load_threshold,
                label=f"before extending {item.function}",
                report=report,
            )
            _base, extra = run_permuter(
                plan,
                scratch,
                out_dir,
                minutes=plan.extend_minutes,
                log_name="permuter-extend.log",
                runner=runner,
                clock=clock,
            )
            result.window_seconds += plan.extend_minutes * 60.0
            result.hit_cap = extra >= plan.extend_minutes * 60.0 * 0.95
            best_dir, best_score = best_output(scratch)
            # The extension re-seeds from the best candidate, so its own
            # window is the one that says whether the search was still
            # descending when it ended.
            result.best_output_mtime_fraction = output_fraction(
                elapsed=extra, best_age=_best_age(best_dir, now)
            )
        result.best_score = best_score
        result.zero_found = best_score == 0
        result.output_dir = str(best_dir) if best_dir is not None else str(out_dir)
    except (PermuterError, OSError, ValueError, subprocess.SubprocessError) as error:
        result.error = str(error)
    result.seconds = clock() - started
    return result


def run_sweep(
    plan: SweepPlan,
    queue: Sequence[QueueItem],
    *,
    carried: Sequence[SweepResult] = (),
    runner: Runner = subprocess.run,
    report: Reporter | None = None,
    on_result: Callable[[list[SweepResult]], None] | None = None,
) -> list[SweepResult]:
    """Search every queued function, recording after each one completes."""

    results: list[SweepResult] = list(carried)
    if plan.jobs == 1:
        for item in queue:
            results.append(search_function(plan, item, runner=runner, report=report))
            if on_result is not None:
                on_result(results)
        return results
    with concurrent.futures.ThreadPoolExecutor(max_workers=plan.jobs) as pool:
        futures = [
            pool.submit(search_function, plan, item, runner=runner, report=report)
            for item in queue
        ]
        for future in concurrent.futures.as_completed(futures):
            results.append(future.result())
            if on_result is not None:
                on_result(results)
    return results


# ---------------------------------------------------------------------------
# Doctor
# ---------------------------------------------------------------------------


@dataclass
class DoctorReport:
    """The preflight one function owes before an hour is spent searching it."""

    function: str
    source: str
    object: str
    flags: tuple[str, ...] = ()
    flags_recovered: bool = False
    objcopy_steps: tuple[str, ...] = ()
    skipped_postprocess: tuple[str, ...] = ()
    replicated: tuple[str, ...] = ()
    base_compiles: bool | None = None
    base_score: int | None = None
    warnings: tuple[str, ...] = ()
    problems: tuple[str, ...] = ()

    @property
    def ok(self) -> bool:
        return not self.problems

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": DOCTOR_SCHEMA,
            "function": self.function,
            "source": self.source,
            "object": self.object,
            "flags": list(self.flags),
            "flags_recovered": self.flags_recovered,
            "objcopy_steps": list(self.objcopy_steps),
            "replicated": list(self.replicated),
            "skipped_postprocess": list(self.skipped_postprocess),
            "base_compiles": self.base_compiles,
            "base_score": self.base_score,
            "warnings": list(self.warnings),
            "problems": list(self.problems),
            "ok": self.ok,
        }


def doctor(
    plan: SweepPlan,
    item: QueueItem,
    *,
    seconds: int = 120,
    check_base: bool = True,
    runner: Runner = subprocess.run,
    clock: Callable[[], float] = time.monotonic,
) -> DoctorReport:
    """Answer the three questions a sweep cannot recover from getting wrong.

    Are these the flags the real build uses; does the scratch replicate the
    post-compile chain; and does the base actually compile to a finite,
    non-zero score. A base score of zero means the scratch is not scoring the
    function under test at all -- a "match" it would report instantly and
    which would not rebuild.
    """

    obj = item.object or object_target(plan.options.object_template, item.source)
    problems: list[str] = []
    try:
        out_dir, scratch, recipe, steps = prepare_scratch(plan, item, runner=runner)
    except (PermuterError, OSError, ValueError, subprocess.SubprocessError) as error:
        return DoctorReport(
            function=item.function,
            source=item.source,
            object=obj,
            problems=(str(error),),
        )
    if not recipe.from_dry_run:
        problems.append(
            f"codegen flags were not recovered from `{plan.options.make} -n {obj}`; "
            "the search would explore whatever the fallback names, which is not "
            "necessarily the ISA the real build uses"
        )
    report = DoctorReport(
        function=item.function,
        source=item.source,
        object=obj,
        flags=recipe.flags,
        flags_recovered=recipe.from_dry_run,
        objcopy_steps=recipe.objcopy_steps,
        skipped_postprocess=recipe.skipped_postprocess,
        replicated=steps,
        warnings=recipe.warnings,
    )
    if not check_base:
        return replace(report, problems=tuple(problems))
    base_score, _elapsed = run_permuter(
        plan,
        scratch,
        out_dir,
        minutes=max(1, seconds // 60),
        log_name="doctor.log",
        runner=runner,
        clock=clock,
    )
    compiles = base_score is not None
    if not compiles:
        problems.append(
            "the scratch base did not produce a score: it did not compile, or "
            f"decomp-permuter failed; read {out_dir / 'doctor.log'}"
        )
    elif base_score == 0:
        problems.append(
            "the base already scores 0, so this scratch is not scoring the "
            "function under test -- check the target assembly and the symbol"
        )
    return replace(
        report,
        base_compiles=compiles,
        base_score=base_score,
        problems=tuple(problems),
    )


def render_doctor(report: DoctorReport) -> list[str]:
    lines = [
        f"permute-doctor {report.function}",
        f"  source           {report.source}",
        f"  object           {report.object}",
        f"  codegen flags    {' '.join(report.flags) or '(none)'} "
        f"[{'make -n' if report.flags_recovered else 'FALLBACK'}]",
    ]
    lines.append(f"  objcopy steps    {len(report.objcopy_steps)}")
    lines.extend(f"    replicated     {step}" for step in report.replicated)
    lines.extend(f"    skipped        {step}" for step in report.skipped_postprocess)
    if report.base_compiles is None:
        lines.append("  base            not checked (--no-base-check)")
    else:
        state = "compiles" if report.base_compiles else "DOES NOT COMPILE"
        lines.append(f"  base            {state}, score {report.base_score}")
    lines.extend(f"  warning         {warning}" for warning in report.warnings)
    lines.extend(f"  problem         {problem}" for problem in report.problems)
    lines.append("  verdict         " + ("ready" if report.ok else "NOT READY"))
    return lines


def write_summary(
    directory: Path, payload: dict[str, Any], table: Sequence[str]
) -> tuple[Path, Path]:
    directory.mkdir(parents=True, exist_ok=True)
    summary_json = directory / "summary.json"
    summary_txt = directory / "summary.txt"
    summary_json.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    summary_txt.write_text("\n".join(table) + "\n", encoding="utf-8")
    return summary_json, summary_txt


__all__ = [
    "DoctorReport",
    "PermuterError",
    "SweepPlan",
    "doctor",
    "import_scratch",
    "prepare_scratch",
    "prepare_target_asm",
    "render_doctor",
    "resolve_plan",
    "run_permuter",
    "run_sweep",
    "search_function",
    "write_summary",
]
