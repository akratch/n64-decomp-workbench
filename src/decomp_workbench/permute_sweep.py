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
import re
import shutil
import subprocess  # nosec B404 - argv-only, never through a shell
import sys
import time
from base64 import b64decode
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field, replace
from functools import partial
from pathlib import Path
from typing import Any, NamedTuple

from .campaign import process_group_arguments, terminate_process_group
from .compare import compare_objects
from .permute import (
    DOCTOR_SCHEMA,
    FIDELITY_DIFFERS,
    FIDELITY_IDENTICAL,
    FIDELITY_UNKNOWN,
    BuildRecipe,
    FidelityAttempt,
    PreserveMacroMode,
    QueueItem,
    Runner,
    ScratchFidelity,
    SweepResult,
    append_compile_steps,
    best_output,
    fidelity_warning,
    macro_attributable,
    object_target,
    output_fraction,
    parse_base_score,
    parse_preserved_macros,
    permuter_argv,
    recipe_report,
    recover_recipe,
    render_settings,
    resolve_preserve_macro_modes,
    retarget_labels,
    retarget_objcopy,
    should_extend,
    wait_for_headroom,
)
from .project_config import PermuterOptions

Reporter = Callable[[str], None]


class PermuterError(RuntimeError):
    """A scratch could not be prepared, or a tool is missing."""


def run_owned(
    argv: Sequence[str],
    *,
    cwd: str | Path | None = None,
    stdout: Any = None,
    stderr: Any = None,
    text: bool = False,
    timeout: float | None = None,
    check: bool = False,
) -> subprocess.CompletedProcess[str]:
    """Run one tool as the owner of its own process group.

    `subprocess.run(timeout=...)` ends the process it started and nothing
    else. decomp-permuter is launched with ``-j``, so that process is the
    parent of a pool of compiling children: on a timeout the parent dies and
    the pool keeps going, into the next function's window and the one after
    that. The reference host's runner accumulated exactly those workers
    until the machine was unusable, and every timing measured afterwards was
    measured under them.

    Signature-compatible with the `subprocess.run` calls this module makes,
    so it is the default runner rather than a special case at one call site:
    ``import.py`` starts a compiler too.
    """

    with subprocess.Popen(  # nosec B603 - argv-only, never through a shell
        list(argv),
        cwd=str(cwd) if cwd is not None else None,
        stdout=stdout,
        stderr=stderr,
        text=text,
        encoding="utf-8" if text else None,
        errors="replace" if text else None,
        **process_group_arguments(),
    ) as process:
        try:
            captured, errors = process.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            terminate_process_group(process)
            captured, errors = process.communicate()
            raise subprocess.TimeoutExpired(
                list(argv), timeout if timeout is not None else 0.0, output=captured
            ) from None
        except BaseException:
            # An interrupt must not leak a pool of workers into the next
            # campaign either.
            terminate_process_group(process)
            raise
    completed = subprocess.CompletedProcess(
        args=list(argv),
        returncode=process.returncode,
        stdout=captured,
        stderr=errors,
    )
    if check:
        completed.check_returncode()
    return completed


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
    #: Compile the scratch base and compare it with the project's own object
    #: for the same translation unit before spending a window searching it.
    check_fidelity: bool = True
    #: Refuse a function whose scratch is not that object, rather than
    #: warning about it. For the runs where a non-transferable score is worse
    #: than no score.
    require_fidelity: bool = False

    @property
    def objdump(self) -> str | None:
        return self.options.objdump

    @property
    def preserve_macro_modes(self) -> tuple[PreserveMacroMode, ...]:
        """The import modes this project tries, in order."""

        return resolve_preserve_macro_modes(
            self.options.preserve_macros, self.options.preserve_macro_modes
        )

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
    objdump: str | None = None,
    check_fidelity: bool = True,
    require_fidelity: bool = False,
) -> SweepPlan:
    """Apply command-line overrides over the project's configured defaults."""

    if permuter_dir is not None:
        options = replace(options, permuter_dir=Path(permuter_dir).expanduser())
    if make is not None:
        options = replace(options, make=make)
    if objdump is not None:
        options = replace(options, objdump=objdump)
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
        check_fidelity=check_fidelity,
        require_fidelity=require_fidelity,
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
    preserve_macros: str | None = None,
    log_name: str = "import.log",
    runner: Runner = run_owned,
) -> Path:
    """Run decomp-permuter's `import.py`, then take ownership of its output.

    ``preserve_macros`` is `import.py`'s own ``--preserve-macros`` regex, and
    the empty string is meaningful there: it means "preserve nothing", so the
    translation unit's real header macros expand into the scratch the way the
    build expands them. ``None`` passes the option at all, leaving the
    settings file's ``[preserve_macros]`` table in charge.
    """

    source = Path(item.source)
    if not source.is_absolute():
        source = plan.root / source
    imported = plan.root / "nonmatchings" / item.function
    if imported.exists():
        shutil.rmtree(imported)
    argv = [
        plan.python,
        str(plan.tool("import.py")),
        str(source),
        str(target_asm),
        "--settings",
        str(settings),
    ]
    if preserve_macros is not None:
        argv += ["--preserve-macros", preserve_macros]
    completed = runner(
        argv,
        cwd=str(plan.root),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        check=False,
    )
    (out_dir / log_name).write_text(completed.stdout or "", encoding="utf-8")
    if completed.returncode != 0 or not imported.is_dir():
        raise PermuterError(
            f"{item.function}: import.py failed; see {out_dir / log_name}"
        )
    scratch = out_dir / "scratch"
    if scratch.exists():
        shutil.rmtree(scratch)
    shutil.move(str(imported), str(scratch))
    return scratch


# ---------------------------------------------------------------------------
# Scratch fidelity
# ---------------------------------------------------------------------------


def expand_permuter_pragmas(source: str) -> str:
    """Turn an imported `base.c` into the source the permuter compiles.

    `import.py` writes `base.c` with its bookkeeping still in it: a
    `latedefine` block holding the macro definitions it hid from the
    preprocessor, and base64 lines standing in for text it could not let
    through. decomp-permuter expands those every time it compiles a
    candidate. The fidelity check has to compile the *same* source the search
    will compile, so it expands them the same way rather than compiling
    `base.c` as written -- which would leave the fake `void gDPPipeSync();`
    declarations in place and quietly compile function calls where the real
    build has an inlined display-list write.
    """

    if "#pragma" not in source:
        return source
    prefix = "#pragma _permuter "
    out: list[str] = []
    same_line = 0
    ignore = 0
    for raw in source.split("\n"):
        line = raw
        stripped = line.strip()
        if stripped.startswith(prefix):
            line = ""
            directive = stripped[len(prefix) :]
            if directive == "sameline start":
                same_line += 1
            elif directive == "sameline end":
                same_line -= 1
            elif directive == "latedefine start":
                ignore += 1
            elif directive == "latedefine end":
                ignore -= 1
            elif directive.startswith("define "):
                line = "#" + directive
            elif directive.startswith("b64literal "):
                line = b64decode(directive.split(" ", 1)[1]).decode("utf-8")
        elif ignore > 0:
            # The fake declarations inside the latedefine block exist only so
            # the permuter's C parser accepts the file. They must not reach a
            # compiler.
            line = ""
        if not same_line:
            line += "\n"
        elif line and out and not out[-1].endswith("\n"):
            line = " " + line.lstrip()
        out.append(line)
    return "".join(out).rstrip() + "\n"


def compile_scratch_base(
    plan: SweepPlan,
    scratch: Path,
    out_dir: Path,
    *,
    runner: Runner = run_owned,
) -> Path:
    """Compile the scratch's unmodified base through its own `compile.sh`.

    Through `compile.sh` specifically, because that is the script the search
    will use: it carries the recovered codegen flags and the replicated
    post-compile chain, and an object built any other way would prove
    something about a build nobody runs.
    """

    base = scratch / "base.c"
    if not base.is_file():
        raise PermuterError(f"the scratch has no base.c at {base}")
    script = scratch / "compile.sh"
    if not script.is_file():
        raise PermuterError(f"the scratch has no compile.sh at {script}")
    source = out_dir / "fidelity-base.c"
    source.write_text(
        expand_permuter_pragmas(base.read_text(encoding="utf-8", errors="replace")),
        encoding="utf-8",
    )
    obj = out_dir / "fidelity-base.o"
    if obj.exists():
        obj.unlink()
    log = out_dir / "fidelity-compile.log"
    with log.open("w", encoding="utf-8") as stream:
        completed = runner(
            [str(script), str(source), "-o", str(obj)],
            cwd=str(plan.root),
            stdout=stream,
            stderr=subprocess.STDOUT,
            check=False,
        )
    if completed.returncode != 0 or not obj.is_file():
        raise PermuterError(f"the scratch base did not compile; see {log}")
    return obj


def check_scratch_fidelity(
    plan: SweepPlan,
    item: QueueItem,
    scratch: Path,
    out_dir: Path,
    *,
    mode: str,
    preserved_macros: tuple[str, ...] | None = None,
    runner: Runner = run_owned,
) -> ScratchFidelity:
    """Is this scratch's object the object the real build produces?

    The comparison is the function's own words in the two objects, through
    the same object oracle every other comparison here uses. It is
    deliberately not a whole-section byte compare: the scratch holds one
    pruned function and the project object holds the whole translation unit,
    so their `.data` and `.rodata` sections differ for reasons that have
    nothing to do with codegen. What does carry across is the function's
    instruction words and the relocations they name -- which is exactly where
    a macro that expands differently shows up, as a different frame, a
    different schedule, or a different symbol being read.
    """

    obj = item.object or object_target(plan.options.object_template, item.source)
    real = Path(obj)
    if not real.is_absolute():
        real = plan.root / real
    unknown = partial(
        ScratchFidelity,
        status=FIDELITY_UNKNOWN,
        mode=mode,
        object=obj,
        preserved_macros=preserved_macros or (),
    )
    if not real.is_file():
        return unknown(
            reason=(
                f"the project's object {obj} is not built, so there is nothing "
                "to compare the scratch against; build it first"
            )
        )
    try:
        candidate = compile_scratch_base(plan, scratch, out_dir, runner=runner)
    except (PermuterError, OSError) as error:
        return unknown(reason=str(error))
    try:
        comparison = compare_objects(
            real, candidate, objdump=plan.objdump, symbol=item.function
        )
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        return unknown(reason=f"could not compare the two objects: {error}")
    if comparison.error:
        return unknown(reason=comparison.error)
    words = comparison.word_mismatches or abs(comparison.instruction_delta)
    if comparison.exact and not words:
        status = FIDELITY_IDENTICAL
        words = 0
    else:
        status = FIDELITY_DIFFERS
        words = words or comparison.raw_word_mismatches
    return ScratchFidelity(
        status=status,
        differing_words=words,
        mode=mode,
        object=obj,
        preserved_macros=preserved_macros or (),
    )


FidelityChecker = Callable[..., ScratchFidelity]


class ScratchPreparation(NamedTuple):
    """One prepared scratch: where it is, how it was built, and whether it
    reproduces the object the project's own build produces."""

    out_dir: Path
    scratch: Path
    recipe: BuildRecipe
    steps: tuple[str, ...]
    fidelity: ScratchFidelity = field(default_factory=ScratchFidelity)


@dataclass(frozen=True)
class _ModeOutcome:
    """What one import mode produced, and how good an answer it is.

    ``rank`` orders the modes when none of them is identical: a measured
    difference beats an unmeasurable one, a smaller difference beats a larger
    one, and the configured mode wins a tie because it is the one the project
    asked for and the only one that lets the permuter reach inside a macro.
    """

    mode: PreserveMacroMode
    fidelity: ScratchFidelity
    scratch: Path
    steps: tuple[str, ...]

    @property
    def rank(self) -> tuple[int, int]:
        order = {FIDELITY_IDENTICAL: 0, FIDELITY_DIFFERS: 1}.get(
            self.fidelity.status, 2
        )
        return (order, self.fidelity.differing_words or 0)


def _import_one_mode(
    plan: SweepPlan,
    item: QueueItem,
    out_dir: Path,
    recipe: BuildRecipe,
    mode: PreserveMacroMode,
    target_asm: Path,
    *,
    single: bool,
    runner: Runner,
) -> tuple[Path, tuple[str, ...], tuple[str, ...] | None]:
    """Import one mode into the scratch, and replicate the recipe onto it."""

    options = plan.options
    log_name = "import.log" if single else f"import-{_mode_slug(mode.name)}.log"
    settings = out_dir / (
        "permuter_settings.toml"
        if single
        else f"permuter_settings-{_mode_slug(mode.name)}.toml"
    )
    settings.write_text(
        render_settings(
            compiler_command=options.compiler_command or "",
            assembler_command=options.assembler_command or "",
            flags=recipe.flags,
            compiler_type=options.compiler_type,
            preserve_macros=mode.macros,
            decompme_compiler=options.decompme_compiler,
        ),
        encoding="utf-8",
    )
    scratch = import_scratch(
        plan,
        item,
        out_dir,
        settings,
        target_asm,
        preserve_macros=mode.regex,
        log_name=log_name,
        runner=runner,
    )
    obj = item.object or object_target(options.object_template, item.source)
    steps = retarget_objcopy(recipe.objcopy_steps, obj)
    append_compile_steps(scratch / "compile.sh", steps)
    (out_dir / "recipe.txt").write_text(
        recipe_report(recipe, steps) + f"import mode: {mode.name}\n", encoding="utf-8"
    )
    preserved = parse_preserved_macros(
        (out_dir / log_name).read_text(encoding="utf-8", errors="replace")
    )
    return scratch, steps, preserved


def _mode_slug(name: str) -> str:
    """A mode name that is safe as a filename component."""

    return re.sub(r"[^A-Za-z0-9_.-]+", "_", name) or "mode"


def prepare_scratch(
    plan: SweepPlan,
    item: QueueItem,
    *,
    runner: Runner = run_owned,
    fidelity_checker: FidelityChecker = check_scratch_fidelity,
) -> ScratchPreparation:
    """Build one function's scratch from the project's *real* recipe.

    When the scratch that recipe produces is not the object the build
    produces, and the difference could be the importer's injected macro
    stubs, the import is retried with narrower -- finally empty -- preserved
    macro sets, and the first mode whose object is identical wins. Giving up
    preserved macros costs the permuter the ability to permute *inside* those
    macro calls; searching an object the build never emits costs the whole
    window.
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
    target_asm = prepare_target_asm(plan.root, item, out_dir)
    modes = plan.preserve_macro_modes if plan.check_fidelity else ()
    if not modes:
        scratch, steps, _preserved = _import_one_mode(
            plan,
            item,
            out_dir,
            recipe,
            PreserveMacroMode("configured", tuple(options.preserve_macros), None),
            target_asm,
            single=True,
            runner=runner,
        )
        return ScratchPreparation(out_dir, scratch, recipe, steps)

    single = len(modes) == 1
    attempts: list[FidelityAttempt] = []
    outcomes: list[_ModeOutcome] = []
    for mode in modes:
        scratch, steps, preserved = _import_one_mode(
            plan, item, out_dir, recipe, mode, target_asm, single=single, runner=runner
        )
        fidelity = fidelity_checker(
            plan,
            item,
            scratch,
            out_dir,
            mode=mode.name,
            preserved_macros=preserved,
            runner=runner,
        )
        outcomes.append(_ModeOutcome(mode, fidelity, scratch, steps))
        attempts.append(
            FidelityAttempt(
                mode=mode.name,
                status=fidelity.status,
                differing_words=fidelity.differing_words,
                preserved_macros=fidelity.preserved_macros,
                reason=fidelity.reason,
            )
        )
        if fidelity.status == FIDELITY_IDENTICAL:
            break
        if not macro_attributable(replace(fidelity, attempts=tuple(attempts))):
            # Nothing was preserved, so a narrower preserve set is the same
            # import again. Whatever this scratch differs by, it is not the
            # macro stubs, and a second window spent importing proves that
            # twice.
            break
    chosen = min(enumerate(outcomes), key=lambda pair: (pair[1].rank, pair[0]))[1]
    if chosen is not outcomes[-1]:
        # The mode being kept is not the one left on disk by the last import.
        scratch, steps, _preserved = _import_one_mode(
            plan,
            item,
            out_dir,
            recipe,
            chosen.mode,
            target_asm,
            single=single,
            runner=runner,
        )
        chosen = _ModeOutcome(chosen.mode, chosen.fidelity, scratch, steps)
    return ScratchPreparation(
        out_dir,
        chosen.scratch,
        recipe,
        chosen.steps,
        replace(chosen.fidelity, attempts=tuple(attempts)),
    )


# ---------------------------------------------------------------------------
# Running
# ---------------------------------------------------------------------------


def run_permuter(
    plan: SweepPlan,
    scratch: Path,
    out_dir: Path,
    *,
    seconds: float,
    log_name: str = "permuter.log",
    runner: Runner = run_owned,
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
                timeout=seconds,
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
    runner: Runner = run_owned,
    clock: Callable[[], float] = time.monotonic,
    now: Callable[[], float] = time.time,
    report: Reporter | None = None,
    fidelity_checker: FidelityChecker = check_scratch_fidelity,
) -> SweepResult:
    """Prepare, search and record one function. Never raises into the batch."""

    result = SweepResult(function=item.function, source=item.source)
    started = clock()
    try:
        out_dir, scratch, recipe, steps, fidelity = prepare_scratch(
            plan, item, runner=runner, fidelity_checker=fidelity_checker
        )
        result.flags = " ".join(recipe.flags) or None
        result.flags_recovered = recipe.from_dry_run
        result.replicated_objcopy = len(steps)
        result.skipped_postprocess = len(recipe.skipped_postprocess)
        result.warnings = list(recipe.warnings)
        result.scratch_fidelity = fidelity.status
        result.scratch_fidelity_words = fidelity.differing_words
        result.scratch_fidelity_mode = fidelity.mode
        result.scratch_fidelity_reason = fidelity.reason
        scratch_warning = fidelity_warning(fidelity, item.function)
        if scratch_warning is not None:
            result.warnings.append(scratch_warning)
        for warning in result.warnings:
            if report is not None:
                report(f"WARNING [{item.function}] {warning}")
        if plan.require_fidelity and fidelity.status != FIDELITY_IDENTICAL:
            # --require-fidelity is for the runs where a score about the wrong
            # object is worse than no score at all. Refusing here spends the
            # import and nothing else.
            raise PermuterError(
                f"--require-fidelity: the scratch for {item.function} is "
                f"{fidelity.summary} against the project's own object"
                + (f" ({fidelity.reason})" if fidelity.reason else "")
            )
        wait_for_headroom(
            plan.load_threshold,
            label=f"before permuting {item.function}",
            report=report,
        )
        base_score, elapsed = run_permuter(
            plan,
            scratch,
            out_dir,
            seconds=plan.minutes * 60.0,
            runner=runner,
            clock=clock,
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
                seconds=plan.extend_minutes * 60.0,
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
    runner: Runner = run_owned,
    report: Reporter | None = None,
    on_result: Callable[[list[SweepResult]], None] | None = None,
    fidelity_checker: FidelityChecker = check_scratch_fidelity,
) -> list[SweepResult]:
    """Search every queued function, recording after each one completes."""

    results: list[SweepResult] = list(carried)
    if plan.jobs == 1:
        for item in queue:
            results.append(
                search_function(
                    plan,
                    item,
                    runner=runner,
                    report=report,
                    fidelity_checker=fidelity_checker,
                )
            )
            if on_result is not None:
                on_result(results)
        return results
    with concurrent.futures.ThreadPoolExecutor(max_workers=plan.jobs) as pool:
        futures = [
            pool.submit(
                search_function,
                plan,
                item,
                runner=runner,
                report=report,
                fidelity_checker=fidelity_checker,
            )
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
    fidelity: ScratchFidelity = field(default_factory=ScratchFidelity)
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
            "scratch_fidelity": self.fidelity.as_dict(),
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
    runner: Runner = run_owned,
    clock: Callable[[], float] = time.monotonic,
    fidelity_checker: FidelityChecker = check_scratch_fidelity,
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
        out_dir, scratch, recipe, steps, fidelity = prepare_scratch(
            plan, item, runner=runner, fidelity_checker=fidelity_checker
        )
    except (PermuterError, OSError, ValueError, subprocess.SubprocessError) as error:
        return DoctorReport(
            function=item.function,
            source=item.source,
            object=obj,
            problems=(str(error),),
        )
    scratch_warnings: list[str] = []
    scratch_note = fidelity_warning(fidelity, item.function)
    if scratch_note is not None:
        if plan.require_fidelity:
            problems.append(scratch_note)
        else:
            scratch_warnings.append(scratch_note)
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
        fidelity=fidelity,
        warnings=recipe.warnings + tuple(scratch_warnings),
    )
    if not check_base:
        return replace(report, problems=tuple(problems))
    base_score, _elapsed = run_permuter(
        plan,
        scratch,
        out_dir,
        seconds=float(seconds),
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
    lines.append(
        f"  scratch object  {report.fidelity.summary}"
        + (f" [{report.fidelity.mode}]" if report.fidelity.mode else "")
    )
    if report.fidelity.reason:
        lines.append(f"    why           {report.fidelity.reason}")
    for attempt in report.fidelity.attempts:
        lines.append(
            f"    mode          {attempt.mode}: {attempt.status}"
            + (
                f" ({attempt.differing_words} word(s))"
                if attempt.differing_words
                else ""
            )
        )
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
    "ScratchPreparation",
    "SweepPlan",
    "check_scratch_fidelity",
    "compile_scratch_base",
    "doctor",
    "expand_permuter_pragmas",
    "import_scratch",
    "prepare_scratch",
    "prepare_target_asm",
    "render_doctor",
    "resolve_plan",
    "run_owned",
    "run_permuter",
    "run_sweep",
    "search_function",
    "write_summary",
]
