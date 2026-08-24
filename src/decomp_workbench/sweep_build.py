"""Compile a wave of candidate sources and score them into one table.

`sweep` already owned both ends of the search loop: the generators emit
sources, `sweep ingest` reads the built objects back. The middle -- *build the
wave* -- was the half every campaign wrote itself. One endgame rewrote it in
three shapes across two agents' sessions (`score_wave.py`, twice more under
other names) and ran roughly eight thousand candidates through it. Each rewrite
re-derived the same four decisions:

* a bounded pool, because an unbounded one starves the machine the reader is
  also using;
* ``nice``, because a wave is background work and the interactive session is
  not;
* skip an object that is already up to date, because a wave is re-run after a
  small edit far more often than it is run fresh;
* and one row per candidate carrying the standard metric columns *plus* a
  watch-row signature, because the signature is what converged when the
  scalars misled.

This module is those decisions, once. It deliberately does not own a project's
build -- the compile command is the project's, given as a ``{source}`` /
``{output}`` template, which is the same boundary `campaign` draws.

**Why this is `sweep build` rather than a new `campaign` mode.** `campaign`
is a per-function lifecycle: registration, persistent state, a ledger, resume,
signals, stop-on-exact. Its engine is the right one for a long-lived search
with a memory. A scoring wave has no memory and wants the opposite defaults --
score everything, keep nothing, print a table -- and it belongs beside the
generators whose output it consumes. So the vocabulary is `sweep`'s, and the
pieces that are genuinely shared (`render_compile_command`, `run_compiler`'s
process-group ownership and timeout) are imported from `campaign` rather than
copied.
"""

from __future__ import annotations

import concurrent.futures
import hashlib
import json
import os
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .campaign import (
    CompilerTimeoutError,
    executable_identity,
    nice_prefix,
    render_compile_command,
    run_compiler,
)
from .compare import TargetObject, compare_candidate, load_target
from .model import Comparison, display_path
from .objdump import discover_objdump
from .sweep import SweepError, read_manifest
from .watch_rows import WatchRow, evaluate_watch_rows, watch_row_payload

__all__ = [
    "BUILD_SCHEMA",
    "DEFAULT_JOBS",
    "DEFAULT_NICE",
    "SORT_ORDERS",
    "BuildResult",
    "SweepBuild",
    "assign_labels",
    "build_lines",
    "collect_sources",
    "run_sweep_build",
]

BUILD_SCHEMA = "decomp-workbench-sweep-build-v1"

#: Small on purpose. A wave runs beside an interactive session, and a pool
#: sized to the machine makes the machine unusable for the person reading the
#: table it is producing.
DEFAULT_JOBS = 4

#: The niceness a wave runs at. Not zero, and not configurable away by
#: accident: background work that competes with the foreground on equal terms
#: is the reason campaigns were run by hand at ``nice -n 10`` in the first
#: place.
DEFAULT_NICE = 10

#: The sidecar recording what each object was built from, so a re-run knows
#: whether it is up to date. Content and command, never mtime alone: a wave is
#: usually re-run *because the compile command changed*, and an mtime check
#: silently keeps every stale object in that case.
CACHE_FILE = ".sweep-build.json"

SORT_ORDERS = ("words", "rows-away", "watch", "name")


class SweepBuildError(SweepError):
    """A wave could not be prepared, built, or scored."""


@dataclass(frozen=True)
class BuildResult:
    """One candidate: how it built, and how it scored."""

    label: str
    source: str
    object_path: str | None
    #: ``compiled``, ``cached`` (the object was already current), ``failed``
    #: (the compiler refused), or ``unreadable`` (it built but objdump could
    #: not be believed). Never silently absent: an unbuilt candidate that
    #: vanishes from the table reads as a candidate that was never tried.
    status: str
    comparison: Comparison | None = None
    detail: str = ""
    watch: dict[str, Any] = field(default_factory=dict)

    @property
    def scored(self) -> bool:
        return self.comparison is not None

    @property
    def signature(self) -> str:
        return str(self.watch.get("watch_signature", ""))

    def as_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "label": self.label,
            "source": self.source,
            "object": self.object_path,
            "status": self.status,
            "detail": self.detail,
        }
        if self.comparison is not None:
            payload["comparison"] = self.comparison.as_dict()
            payload.update(
                verdict=self.comparison.verdict,
                words=self.comparison.word_mismatches,
                raw=self.comparison.raw_word_mismatches,
                opcodes=self.comparison.opcode_mismatches,
                regs=self.comparison.register_mismatches,
                fp=self.comparison.fp_register_mismatches,
                gaps=self.comparison.aligned_gaps,
                insns=self.comparison.candidate_instructions,
                frame=self.comparison.candidate_frame_size,
                exact=self.comparison.exact,
            )
        payload.update(self.watch)
        return payload


def _sort_key(item: BuildResult, order: str) -> tuple[Any, ...]:
    """Rank one row. Every order ends on the label, so ties never reshuffle.

    A wave is read twice: once when it finishes and once after the next edit.
    A table whose equal rows swap places between those two readings is a table
    nobody can diff, so the label is the final tiebreak in all four orders.
    """

    comparison = item.comparison
    if comparison is None:
        return (1, 0, 0, 0, item.label)
    if order == "name":
        return (0, item.label)
    if order == "watch":
        # Most healed columns first, then the ordinary distance. The signature
        # is a fitness function, not a metric: it is read to see *which*
        # mechanisms healed, and sorting on the count groups the candidates
        # that healed the same ones together.
        broken = int(item.watch.get("watch_broken", 0))
        unknown = int(item.watch.get("watch_out_of_range", 0))
        return (
            0,
            broken + unknown,
            item.signature,
            comparison.word_mismatches,
            item.label,
        )
    if order == "rows-away":
        layout = comparison.layout or {}
        rows_away = layout.get("rows_away")
        return (
            0,
            comparison.word_mismatches if rows_away is None else int(rows_away),
            comparison.word_mismatches,
            item.label,
        )
    return (
        0,
        comparison.word_mismatches,
        comparison.raw_word_mismatches,
        comparison.opcode_mismatches,
        abs(comparison.instruction_delta),
        item.label,
    )


@dataclass(frozen=True)
class SweepBuild:
    """A whole wave: what was asked for, what happened, and the table."""

    target: str
    template: str
    objects: str
    jobs: int
    nice: int
    watch: tuple[WatchRow, ...]
    results: tuple[BuildResult, ...]
    order: str = "words"
    #: File stems more than one input source shares. Reported rather than
    #: silently disambiguated: two candidates with one name is usually two
    #: generator runs pointed at one wave, and the reader wants to know.
    colliding_stems: tuple[str, ...] = ()

    @property
    def ranked(self) -> tuple[BuildResult, ...]:
        return tuple(
            sorted(
                (item for item in self.results if item.scored),
                key=lambda item: _sort_key(item, self.order),
            )
        )

    @property
    def unscored(self) -> tuple[BuildResult, ...]:
        return tuple(
            sorted(
                (item for item in self.results if not item.scored),
                key=lambda item: item.label,
            )
        )

    def count(self, status: str) -> int:
        return sum(1 for item in self.results if item.status == status)

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": BUILD_SCHEMA,
            "target": self.target,
            "compile_command": self.template,
            "objects": self.objects,
            "jobs": self.jobs,
            "nice": self.nice,
            "order": self.order,
            "watch_row_set": [entry.as_dict() for entry in self.watch],
            "candidate_count": len(self.results),
            "compiled": self.count("compiled"),
            "cached": self.count("cached"),
            "failed": self.count("failed"),
            "unreadable": self.count("unreadable"),
            "colliding_stems": list(self.colliding_stems),
            "results": [item.as_dict() for item in self.ranked],
            "unscored": [item.as_dict() for item in self.unscored],
        }


def collect_sources(
    inputs: Iterable[str | Path], *, suffix: str = ".c"
) -> tuple[Path, ...]:
    """Expand files, directories and sweep manifests into one ordered list.

    A directory contributes its ``*.c`` in sorted order; a directory holding a
    ``sweep.json`` contributes that manifest's variants instead, in manifest
    order, so a generated family builds in the order its own catalogue
    declares. Duplicates are dropped rather than built twice, keeping the
    first mention.

    A manifest variant whose file is missing is still returned. It cannot
    build, and `run_sweep_build` gives it a ``failed`` row saying so -- which
    is the invariant `BuildResult.status` states: a candidate that vanishes
    from the table reads as a candidate that was never tried, and the
    generator that declared it is exactly the thing the reader needs told
    about.
    """

    found: list[Path] = []
    seen: set[Path] = set()

    def add(path: Path) -> None:
        resolved = path.expanduser().resolve()
        if resolved in seen:
            return
        seen.add(resolved)
        found.append(resolved)

    for entry in inputs:
        path = Path(entry).expanduser()
        if path.is_dir():
            manifest_path = path / "sweep.json"
            if manifest_path.is_file():
                manifest = read_manifest(manifest_path)
                for variant in manifest.variants:
                    add(path / variant.filename)
                continue
            for candidate in sorted(path.glob(f"*{suffix}")):
                add(candidate)
            continue
        if path.is_file():
            add(path)
            continue
        raise SweepBuildError(
            f"{path} is neither a file nor a directory. `sweep build` takes "
            "candidate sources, directories of them, or a generated sweep "
            "directory holding sweep.json."
        )
    if not found:
        raise SweepBuildError(
            "no candidate sources found. A directory contributes its *"
            f"{suffix} files; a sweep directory contributes its manifest's "
            "variants."
        )
    return tuple(found)


def assign_labels(sources: Sequence[Path]) -> dict[Path, str]:
    """Give every source a label unique across the whole wave.

    The label names the row in the table, the object on disk, and the cache
    entry, so two sources sharing one stem -- ``variants/a/hoist.c`` and
    ``variants/b/hoist.c``, which is what two generator runs produce -- used
    to race to compile the same ``hoist.o`` and then score whichever one won
    twice, once under each candidate's name. A colliding stem therefore keeps
    the stem and gains a short digest of its own path.
    """

    counts = Counter(source.stem for source in sources)
    labels: dict[Path, str] = {}
    for source in sources:
        if counts[source.stem] == 1:
            labels[source] = source.stem
            continue
        digest = hashlib.sha256(str(source).encode("utf-8")).hexdigest()[:8]
        labels[source] = f"{source.stem}-{digest}"
    return labels


def _colliding_stems(sources: Sequence[Path]) -> tuple[str, ...]:
    """Return the stems more than one source in the wave shares."""

    counts = Counter(source.stem for source in sources)
    return tuple(sorted(stem for stem, count in counts.items() if count > 1))


def _fingerprint(
    source: Path, command: Sequence[str], *, compiler: Mapping[str, str | None]
) -> str:
    """Identify what an object was built from.

    Source bytes, the command, *and* the compiler's own identity. The last is
    what `campaign`'s cache key has always carried (`candidate_provenance`):
    swapping the toolchain behind an unchanged path leaves source and command
    identical, and without the compiler's hash a whole wave reports ``cached``
    while serving objects the previous toolchain built.
    """

    digest = hashlib.sha256()
    digest.update(source.read_bytes())
    digest.update(b"\0")
    digest.update("\0".join(command).encode("utf-8"))
    digest.update(b"\0")
    digest.update(
        json.dumps(compiler, sort_keys=True, separators=(",", ":")).encode("utf-8")
    )
    return digest.hexdigest()


def _read_cache(directory: Path) -> dict[str, str]:
    try:
        payload = json.loads((directory / CACHE_FILE).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(payload, dict):
        return {}
    return {str(key): str(value) for key, value in payload.items()}


def _write_cache(directory: Path, entries: dict[str, str]) -> None:
    try:
        (directory / CACHE_FILE).write_text(
            json.dumps(entries, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
    except OSError:
        # A wave whose sidecar cannot be written is a wave that rebuilds next
        # time. That is a cost, not a failure, and losing the table over it
        # would be the worse trade.
        pass


def _compile_one(
    source: Path,
    *,
    output: Path,
    template: str,
    niceness: int,
    environment: dict[str, str],
    compile_cwd: Path,
    timeout: float | None,
    cached_fingerprint: str | None,
    compiler: Mapping[str, str | None],
) -> tuple[str, str, str]:
    """Build one candidate. Returns ``(status, detail, fingerprint)``."""

    command = nice_prefix(niceness) + render_compile_command(template, source, output)
    fingerprint = _fingerprint(source, command, compiler=compiler)
    if (
        cached_fingerprint == fingerprint
        and output.is_file()
        and output.stat().st_size > 0
    ):
        return "cached", "", fingerprint
    output.parent.mkdir(parents=True, exist_ok=True)
    try:
        result = run_compiler(
            command,
            environment=environment,
            compile_cwd=compile_cwd,
            timeout=timeout,
        )
    except CompilerTimeoutError as error:
        return "failed", str(error), fingerprint
    except OSError as error:
        return "failed", f"cannot run the compiler: {error}", fingerprint
    if result.returncode or not output.is_file() or output.stat().st_size == 0:
        detail = (result.stderr.strip() or result.stdout.strip()) or (
            "the compiler reported success but produced no object"
        )
        return "failed", detail.splitlines()[-1] if detail else "", fingerprint
    return "compiled", "", fingerprint


def run_sweep_build(
    sources: Sequence[Path],
    *,
    target: str | Path,
    template: str,
    objects: str | Path,
    jobs: int = DEFAULT_JOBS,
    niceness: int = DEFAULT_NICE,
    watch: Sequence[WatchRow] = (),
    objdump: str | None = None,
    symbol: str | None = None,
    section: str = ".text",
    object_suffix: str = ".o",
    environment: dict[str, str] | None = None,
    compile_cwd: str | Path | None = None,
    timeout: float | None = 300.0,
    order: str = "words",
    refresh: bool = False,
) -> SweepBuild:
    """Compile every source at ``nice``, score it, and return the wave.

    Compilation fans out to ``jobs`` workers; scoring is serial and in
    process, because the target is disassembled once and reused. That split is
    deliberate: the compiler is the expensive part and the only part worth
    parallelizing, and a scoring pool would re-disassemble the target per
    worker for no gain.
    """

    if jobs < 1:
        raise SweepBuildError("--jobs must be at least 1")
    if order not in SORT_ORDERS:
        raise SweepBuildError(
            f"unknown --sort {order!r}; expected one of " + ", ".join(SORT_ORDERS)
        )
    target_path = Path(target).expanduser().resolve()
    if not target_path.is_file():
        raise SweepBuildError(f"target object does not exist: {target_path}")
    object_dir = Path(objects).expanduser().resolve()
    object_dir.mkdir(parents=True, exist_ok=True)
    cwd = (
        Path(compile_cwd).expanduser().resolve()
        if compile_cwd
        else Path.cwd().resolve()
    )
    if not cwd.is_dir():
        raise SweepBuildError(f"compiler working directory does not exist: {cwd}")
    env = dict(os.environ) if environment is None else dict(environment)
    cache = {} if refresh else _read_cache(object_dir)
    fresh: dict[str, str] = {}

    labels = assign_labels(sources)
    plan = [
        (source, object_dir / f"{labels[source]}{object_suffix}") for source in sources
    ]
    # The compiler is the same for every candidate in a wave, so its identity
    # is read once here rather than per source: `_fingerprint` needs it, and
    # hashing the binary once per candidate would cost a wave real time.
    compiler = (
        executable_identity(
            render_compile_command(template, sources[0], object_dir / "probe.o"),
            cwd=cwd,
        )
        if sources
        else {}
    )
    outcomes: dict[Path, tuple[str, str, str]] = {
        source: ("failed", "the candidate source does not exist", "")
        for source, _output in plan
        if not source.is_file()
    }
    with concurrent.futures.ThreadPoolExecutor(max_workers=jobs) as pool:
        futures = {
            pool.submit(
                _compile_one,
                source,
                output=output,
                template=template,
                niceness=niceness,
                environment=env,
                compile_cwd=cwd,
                timeout=timeout,
                cached_fingerprint=cache.get(labels[source]),
                compiler=compiler,
            ): source
            for source, output in plan
            if source not in outcomes
        }
        for future in concurrent.futures.as_completed(futures):
            source = futures[future]
            try:
                outcomes[source] = future.result()
            except Exception as error:  # one bad build, not a dead wave
                outcomes[source] = ("failed", f"{type(error).__name__}: {error}", "")

    objdump_path = discover_objdump(objdump)
    loaded: TargetObject = load_target(
        target_path, objdump=objdump_path, symbol=symbol, section=section
    )
    results: list[BuildResult] = []
    for source, output in plan:
        status, detail, fingerprint = outcomes.get(source, ("failed", "not built", ""))
        if status in {"compiled", "cached"} and fingerprint:
            fresh[labels[source]] = fingerprint
        if status == "failed":
            results.append(
                BuildResult(
                    label=labels[source],
                    source=display_path(source),
                    object_path=None,
                    status=status,
                    detail=detail,
                )
            )
            continue
        try:
            comparison = compare_candidate(
                loaded, output, objdump=objdump_path, section=section
            )
        except (OSError, RuntimeError, ValueError) as error:
            results.append(
                BuildResult(
                    label=labels[source],
                    source=display_path(source),
                    object_path=display_path(output),
                    status="unreadable",
                    detail=str(error).splitlines()[0] if str(error) else "",
                )
            )
            continue
        watch_payload: dict[str, Any] = {}
        if watch:
            watch_payload = watch_row_payload(
                evaluate_watch_rows(
                    watch,
                    diff_sites=comparison.diff_sites,
                    compared_rows=max(
                        comparison.target_instructions,
                        comparison.candidate_instructions,
                    ),
                )
            )
        results.append(
            BuildResult(
                label=labels[source],
                source=display_path(source),
                object_path=display_path(output),
                status=status,
                comparison=comparison,
                watch=watch_payload,
            )
        )
    _write_cache(object_dir, fresh)
    return SweepBuild(
        target=display_path(target_path),
        template=template,
        objects=display_path(object_dir),
        jobs=jobs,
        nice=niceness,
        watch=tuple(watch),
        results=tuple(results),
        order=order,
        colliding_stems=_colliding_stems(sources),
    )


def _column(value: object) -> str:
    return "-" if value is None else str(value)


def build_lines(wave: SweepBuild, *, limit: int = 40) -> list[str]:
    """Render the wave as one scored table, then everything that did not."""

    header_watch = " ".join(entry.label for entry in wave.watch)
    signature_width = max(len(header_watch), len(wave.watch)) if wave.watch else 0
    lines = [
        f"sweep build: {len(wave.results)} candidate(s) -> {wave.target}",
        f"{wave.count('compiled')} compiled, {wave.count('cached')} already "
        f"current, {wave.count('failed')} failed, "
        f"{wave.count('unreadable')} unreadable  "
        f"(jobs={wave.jobs}, nice={wave.nice})",
        "",
    ]
    if wave.colliding_stems:
        shown = ", ".join(wave.colliding_stems[:8])
        more = len(wave.colliding_stems) - 8
        lines.extend(
            (
                f"note: {len(wave.colliding_stems)} file name(s) appear in more "
                f"than one input directory ({shown}"
                + (f", +{more} more" if more > 0 else "")
                + "). Each candidate still gets its own object and row; the "
                "labels below carry a short path digest to tell them apart.",
                "",
            )
        )
    if wave.watch:
        lines.extend(
            (
                f"watch rows (. healed, X broken, ? out of range): {header_watch}",
                "",
            )
        )
    signature_column = "sig".ljust(signature_width) + "  " if wave.watch else ""
    lines.append(
        f" words   raw  opcodes  regs   fp  gaps  insns   frame  "
        f"{signature_column}verdict                    candidate"
    )
    for item in wave.ranked[:limit]:
        comparison = item.comparison
        assert comparison is not None
        signature = item.signature.ljust(signature_width) + "  " if wave.watch else ""
        lines.append(
            f"{comparison.word_mismatches:>6} "
            f"{comparison.raw_word_mismatches:>5} "
            f"{comparison.opcode_mismatches:>8} "
            f"{comparison.register_mismatches:>5} "
            f"{comparison.fp_register_mismatches:>4} "
            f"{comparison.aligned_gaps:>5} "
            f"{comparison.candidate_instructions:>6} "
            f"{_column(comparison.candidate_frame_size):>7}  "
            f"{signature}"
            f"{comparison.verdict:<26} {item.label}"
        )
    if len(wave.ranked) > limit:
        lines.append(
            f" ... {len(wave.ranked) - limit} more scored candidate(s); "
            "--limit 0 prints every row"
        )
    if wave.unscored:
        lines.extend(("", f"not scored ({len(wave.unscored)}):"))
        for item in wave.unscored[:limit]:
            lines.append(f"  {item.status:<11} {item.label}  {item.detail}")
        if len(wave.unscored) > limit:
            lines.append(f"  ... {len(wave.unscored) - limit} more")
    exact = [item for item in wave.ranked if item.comparison and item.comparison.exact]
    if exact:
        lines.extend(
            (
                "",
                f"EXACT: {', '.join(item.label for item in exact)}. "
                "`compare --json` the object before believing it, and run the "
                "project's own link/ROM verification: a wave scores objects, "
                "not builds.",
            )
        )
    lines.extend(
        (
            "",
            f"objects in {wave.objects}; a re-run skips any whose source and "
            "compile command are unchanged (--refresh rebuilds every one).",
        )
    )
    return lines
