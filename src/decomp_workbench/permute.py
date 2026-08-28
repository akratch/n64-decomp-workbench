"""Drive decomp-permuter over a queue of functions with scratch fidelity.

Every host that runs decomp-permuter at campaign scale re-invents the same
batch loop, and each re-invention re-introduces the same three faults that
make a search answer the wrong question:

1. **The scratch searches the wrong ISA.** decomp-permuter's importer
   defaults to ``-mips1``; a project that builds ``-mips2`` then gets a
   search whose every candidate is compiled for a target the real build
   never emits. Recovering the flags from ``make -n <object>`` fixes it,
   but only if the source is touched first: ``make -n`` prints nothing for
   an up-to-date object, so the naive recovery silently recovers nothing.
2. **The scratch object is not the real object.** A translation unit whose
   build applies a post-compile ``objcopy`` (``--redefine-sym`` and
   friends) produces a scratch object the real link would never accept, so
   a score of zero in the scratch does not transfer.
3. **The score is normalized.** Without ``--stack-diffs`` the scorer
   normalizes stack offsets and reports zero for a spill at the wrong
   slot.

This module is the parser and the policy for those three, plus the queue
mechanics (closest-first ordering, resume, load gating, the score-trend
extension) around them. It executes decomp-permuter; it does not decide
what a result means, and it deliberately stops short of *promotion*:
splicing a winner into a project's source and proving the byte-identical
rebuild is host-specific, and belongs in the project's own repository
where the authoritative build lives.
"""

from __future__ import annotations

import json
import os
import re
import subprocess  # nosec B404 - argv-only, never through a shell
import time
from collections.abc import Callable, Iterable, Sequence
from dataclasses import asdict, dataclass, field, fields, replace
from pathlib import Path
from typing import Any

#: Flags that shape codegen and therefore must match the real per-file build
#: exactly. Everything else on the recovered command line (``-I``, ``-D``,
#: ``-c``, ``-o``) is supplied by the project's configured base command.
CODEGEN_FLAG_RE = re.compile(
    r"-mips[0-9]|-O[0-9]|-Wo,[^ ]*|-Wab,[^ ]*|-g[0-9]?(?= |$)|-(?:32|n32|64)(?= |$)"
)

#: Post-compile passes a scratch cannot replicate. A Python pass over the
#: object is normally digest-guarded against the *matched* bytes and would
#: abort, or worse silently lie, on a permuted object.
DEFAULT_SKIP_POSTPROCESS = (r"\.py\b",)

#: `glabel`-style directives a target `.s` uses to name a function.
LABEL_RE = re.compile(r"^\s*(?:glabel|endlabel|jlabel|dlabel)\s+(\S+)", re.MULTILINE)

#: What the permuter prints once it has scored the unmodified base.
BASE_SCORE_RE = re.compile(r"base score = (\d+)")

#: Ranking rank for a function the ranking file does not mention: last.
UNRANKED = 10**9

SWEEP_SCHEMA = "decomp-workbench-permute-sweep-v1"
DOCTOR_SCHEMA = "decomp-workbench-permute-doctor-v1"

Runner = Callable[..., "subprocess.CompletedProcess[str]"]
LoadReader = Callable[[], float]


def _default_load() -> float:
    try:
        return os.getloadavg()[0]
    except (OSError, AttributeError):  # pragma: no cover - Windows
        return 0.0


# ---------------------------------------------------------------------------
# Queue
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class QueueItem:
    """One function to search, and the inputs its scratch needs."""

    function: str
    source: str
    asm: str | None = None
    object: str | None = None
    asm_symbol: str | None = None
    label: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {key: value for key, value in asdict(self).items() if value is not None}


def _queue_item(payload: Any, *, origin: str) -> QueueItem:
    if not isinstance(payload, dict):
        raise ValueError(f"{origin}: each queue entry must be a JSON object")
    unknown = set(payload) - {name.name for name in fields(QueueItem)}
    if unknown:
        raise ValueError(f"{origin}: unknown queue keys: {', '.join(sorted(unknown))}")
    for required in ("function", "source"):
        value = payload.get(required)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{origin}: queue entry needs a non-empty {required!r}")
    return QueueItem(
        function=str(payload["function"]),
        source=str(payload["source"]),
        asm=_optional_text(payload.get("asm"), origin, "asm"),
        object=_optional_text(payload.get("object"), origin, "object"),
        asm_symbol=_optional_text(payload.get("asm_symbol"), origin, "asm_symbol"),
        label=_optional_text(payload.get("label"), origin, "label"),
    )


def _optional_text(value: Any, origin: str, name: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{origin}: {name} must be a non-empty string")
    return value


def load_queue(path: str | Path) -> tuple[QueueItem, ...]:
    """Read a queue from JSON, or from one ``function source [asm]`` per line.

    The workbench cannot discover a project's own unmatched-function queue --
    the marker is a project convention (`#ifdef NON_MATCHING`, an objdiff
    report, a ranking) -- so the queue is an input. Both spellings exist
    because a project script usually already emits one of them.
    """

    origin = Path(path).name
    text = Path(path).expanduser().read_text(encoding="utf-8")
    stripped = text.lstrip()
    if stripped.startswith(("{", "[")):
        payload = json.loads(text)
        rows = payload.get("functions", []) if isinstance(payload, dict) else payload
        if not isinstance(rows, list):
            raise ValueError(
                f"{origin}: queue JSON must be a list, or hold 'functions'"
            )
        return tuple(_queue_item(row, origin=origin) for row in rows)
    items: list[QueueItem] = []
    for number, line in enumerate(text.splitlines(), start=1):
        entry = line.split("#", 1)[0].strip()
        if not entry:
            continue
        parts = entry.split()
        if len(parts) < 2:
            raise ValueError(
                f"{origin}:{number}: expected 'function source [asm]', got {entry!r}"
            )
        items.append(
            QueueItem(
                function=parts[0],
                source=parts[1],
                asm=parts[2] if len(parts) > 2 else None,
            )
        )
    return tuple(items)


def load_ranking(path: str | Path | None) -> dict[str, tuple[int, int]]:
    """Read ``{name: (differing_words, size_bytes)}`` from a ranking report."""

    if path is None:
        return {}
    source = Path(path).expanduser()
    if not source.is_file():
        return {}
    payload = json.loads(source.read_text(encoding="utf-8"))
    rows = payload.get("functions", payload) if isinstance(payload, dict) else payload
    ranking: dict[str, tuple[int, int]] = {}
    if not isinstance(rows, list):
        return ranking
    for row in rows:
        if not isinstance(row, dict):
            continue
        name = row.get("name") or row.get("function") or row.get("symbol")
        words = row.get("differing_words")
        if (
            isinstance(name, str)
            and isinstance(words, int)
            and not isinstance(words, bool)
        ):
            size = row.get("size_bytes")
            ranking[name] = (words, size if isinstance(size, int) else 0)
    return ranking


def order_queue(
    items: Sequence[QueueItem], ranking: dict[str, tuple[int, int]]
) -> tuple[QueueItem, ...]:
    """Closest first: fewest differing words, then smallest, then by name.

    A function the ranking does not mention sorts last rather than first: an
    unranked entry is unmeasured, not close, and a sweep that spends its
    first hour on unmeasured functions reports "queue exhausted" having never
    reached the ones a ranking already called near-matches.
    """

    return tuple(
        sorted(
            items,
            key=lambda item: (ranking.get(item.function, (UNRANKED, 0)), item.function),
        )
    )


# ---------------------------------------------------------------------------
# Build-recipe recovery
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class BuildRecipe:
    """What the project's real build does to one translation unit's object.

    ``flags`` are the codegen flags on its compile line; ``objcopy_steps`` is
    the post-compile chain, with the real object path still intact.
    ``from_dry_run`` is false when nothing could be recovered and the caller
    fell back -- the single most important field in the record, because a
    fallback means the search may be exploring the wrong ISA.
    """

    flags: tuple[str, ...] = ()
    objcopy_steps: tuple[str, ...] = ()
    skipped_postprocess: tuple[str, ...] = ()
    from_dry_run: bool = False
    object: str | None = None
    warnings: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return {
            "object": self.object,
            "flags": list(self.flags),
            "objcopy_steps": list(self.objcopy_steps),
            "skipped_postprocess": list(self.skipped_postprocess),
            "from_dry_run": self.from_dry_run,
            "warnings": list(self.warnings),
        }


def join_continuations(text: str) -> str:
    """Join ``\\``-newline continuations before parsing a printed recipe.

    Make echoes a recipe verbatim, so a compile line commonly arrives split
    across two lines with the codegen flags on the *second* one -- the line
    that does not name the compiler. A parser that reads line by line finds
    the compiler on one line, no flags on it, and silently recovers nothing.
    """

    return text.replace("\\\n", " ")


def parse_dry_run(
    text: str,
    *,
    obj: str,
    compiler: str | None = None,
    skip_postprocess: Sequence[str] = DEFAULT_SKIP_POSTPROCESS,
) -> BuildRecipe:
    """Extract codegen flags and the post-compile chain from ``make -n``.

    ``compiler`` narrows which of the object's lines is the compile line. It
    is optional: with no marker, the first line naming the object that is not
    an ``objcopy`` chain and does carry an ISA flag wins.
    """

    skips = tuple(re.compile(pattern) for pattern in skip_postprocess)
    flags: tuple[str, ...] = ()
    objcopy_steps: list[str] = []
    skipped: list[str] = []
    for line in join_continuations(text).splitlines():
        if obj not in line:
            continue
        is_compile = compiler in line if compiler else False
        if "objcopy" in line and not is_compile:
            for segment in (part.strip() for part in line.split("&&")):
                if not segment:
                    continue
                if any(skip.search(segment) for skip in skips):
                    skipped.append(segment)
                elif "objcopy" in segment:
                    objcopy_steps.append(segment)
                else:
                    skipped.append(segment)
            continue
        if flags:
            continue
        if compiler is not None and not is_compile:
            continue
        found = tuple(dict.fromkeys(CODEGEN_FLAG_RE.findall(line)))
        if any(flag.startswith("-mips") for flag in found):
            flags = found
    warnings: tuple[str, ...] = ()
    if not flags:
        warnings = (
            f"could not recover real compile flags for {obj}: the scratch will "
            "use the configured fallback and may search the wrong ISA. Check "
            "that the object target is spelled the way the build spells it.",
        )
    return BuildRecipe(
        flags=flags,
        objcopy_steps=tuple(objcopy_steps),
        skipped_postprocess=tuple(skipped),
        from_dry_run=bool(flags),
        object=obj,
        warnings=warnings,
    )


def object_target(template: str, source: str) -> str:
    """Render a Make object target for one source path."""

    path = Path(source)
    return template.format(
        source=path.as_posix(),
        stem=path.stem,
        name=path.name,
        parent=path.parent.as_posix(),
    )


def recover_recipe(
    root: Path,
    item: QueueItem,
    *,
    make: str = "make",
    object_template: str = "build/{source}.o",
    compiler: str | None = None,
    fallback_flags: Sequence[str] = (),
    skip_postprocess: Sequence[str] = DEFAULT_SKIP_POSTPROCESS,
    runner: Runner = subprocess.run,
    timeout: float = 120.0,
    touch: bool = True,
) -> BuildRecipe:
    """Recover one object's real recipe by asking the build to describe it.

    The source is touched first. ``make -n`` prints nothing at all for an
    up-to-date object, and "nothing" parses as "no flags found", which is
    exactly the silent wrong-ISA search this command exists to prevent.
    """

    obj = item.object or object_target(object_template, item.source)
    source_path = root / item.source
    if touch and source_path.is_file():
        try:
            os.utime(source_path, None)
        except OSError:  # pragma: no cover - permission-dependent
            pass
    try:
        completed = runner(
            [make, "-n", obj],
            cwd=str(root),
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as error:
        recipe = BuildRecipe(
            object=obj,
            warnings=(f"could not run `{make} -n {obj}`: {error}",),
        )
    else:
        recipe = parse_dry_run(
            completed.stdout or "",
            obj=obj,
            compiler=compiler,
            skip_postprocess=skip_postprocess,
        )
    if not recipe.flags and fallback_flags:
        recipe = replace(recipe, flags=tuple(fallback_flags))
    return recipe


def retarget_objcopy(
    steps: Sequence[str], obj: str, output: str = '"$OUTPUT"'
) -> tuple[str, ...]:
    """Point the recovered post-compile chain at the scratch's own object."""

    return tuple(step.replace(obj, output) for step in steps)


# ---------------------------------------------------------------------------
# Scratch preparation
# ---------------------------------------------------------------------------


def render_settings(
    *,
    compiler_command: str,
    assembler_command: str,
    flags: Sequence[str],
    compiler_type: str = "ido",
    preserve_macros: Sequence[str] = (),
    decompme_compiler: str | None = None,
) -> str:
    """Render a decomp-permuter settings file carrying the *real* flags."""

    command = " ".join(part for part in (compiler_command.strip(), *flags) if part)
    lines = [
        f'compiler_type = "{compiler_type}"',
        'compiler_command = """',
        command,
        '"""',
        f"assembler_command = {json.dumps(assembler_command)}",
    ]
    if preserve_macros:
        lines.append("")
        lines.append("[preserve_macros]")
        for entry in preserve_macros:
            pattern, _, kind = entry.partition("=")
            lines.append(f"{json.dumps(pattern.strip())} = {json.dumps(kind.strip())}")
    if decompme_compiler:
        executable = compiler_command.split()[0] if compiler_command.split() else "cc"
        lines.extend(
            (
                "",
                "[decompme.compilers]",
                f"{json.dumps(executable)} = {json.dumps(decompme_compiler)}",
            )
        )
    return "\n".join(lines) + "\n"


def retarget_labels(text: str, *, old: str, new: str) -> str:
    """Rename a target `.s`'s own function labels, and nothing else.

    Splat names an overlay function from the ROM address it disassembled,
    while the C source uses the name a human gave it; decomp-permuter's
    importer looks for the `.s` file's name in the C and fails. This is a
    metadata rename of the label pair, in a copy, never in the project's
    own extracted assembly, and never an instruction word.
    """

    if old == new:
        return text
    return re.sub(r"\b" + re.escape(old) + r"\b", new, text)


def recipe_report(recipe: BuildRecipe, replicated: Sequence[str]) -> str:
    """Render the human record of what the scratch did and did not replicate."""

    origin = "make -n" if recipe.from_dry_run else "fallback (NOT the real build)"
    lines = [f"flags: {' '.join(recipe.flags) or '(none)'} [{origin}]"]
    lines.extend(f"replicated: {step}" for step in replicated)
    lines.extend(
        f"skipped (not replicable): {step}" for step in recipe.skipped_postprocess
    )
    lines.extend(f"warning: {warning}" for warning in recipe.warnings)
    return "\n".join(lines) + "\n"


def append_compile_steps(compile_script: Path, steps: Sequence[str]) -> None:
    """Append the retargeted post-compile chain to the scratch `compile.sh`."""

    if not steps:
        return
    with compile_script.open("a", encoding="utf-8") as stream:
        stream.write("\n")
        for step in steps:
            stream.write(step + "\n")


# ---------------------------------------------------------------------------
# Run policy
# ---------------------------------------------------------------------------


def wait_for_headroom(
    threshold: float,
    *,
    label: str = "",
    load: LoadReader = _default_load,
    sleep: Callable[[float], None] = time.sleep,
    interval: float = 15.0,
    report: Callable[[str], None] | None = None,
) -> int:
    """Block until the one-minute load average is under ``threshold``.

    An unthrottled fleet of permuter instances is the fastest way to make a
    workstation unusable; every compile-heavy launch gates on headroom first.
    Returns how many waits happened, so a caller can report the stall.
    """

    if threshold <= 0:
        return 0
    waited = 0
    while True:
        current = load()
        if current < threshold:
            return waited
        if waited == 0 and report is not None:
            report(f"load {current:.1f} >= {threshold:.1f}; waiting {label}".rstrip())
        sleep(interval)
        waited += 1


def should_extend(
    *,
    elapsed: float,
    minutes: float,
    best_score: int | None,
    best_age: float | None,
    extend_minutes: float,
) -> bool:
    """Was the search still descending when the wall clock cut it off?

    Only then is more time the right answer. A run whose best result landed
    early and then sat for the rest of the window has plateaued, and a second
    window buys nothing: search time is not the fix for a plateau. The test
    is "best result inside the final third of the window", plus the run
    actually having hit its cap, plus a score that is neither absent nor
    already zero.
    """

    if extend_minutes <= 0 or best_score is None or best_score == 0:
        return False
    if best_age is None:
        return False
    window = minutes * 60.0
    if window <= 0 or elapsed < window * 0.95:
        return False
    return best_age < window / 3.0


def output_fraction(*, elapsed: float, best_age: float | None) -> float | None:
    """Where in the window the best output landed, as a 0..1 fraction.

    Computed from the output directory's mtime because that is the only
    timestamp decomp-permuter leaves behind: it writes an output directory
    when it improves on the score, so the newest one's age is how long the
    search ran after its last improvement. 1.0 means "improved as the clock
    stopped it"; 0.1 means "found it in the first minutes and then sat".
    """

    if best_age is None or elapsed <= 0:
        return None
    return min(1.0, max(0.0, (elapsed - best_age) / elapsed))


def best_output(scratch: Path) -> tuple[Path | None, int | None]:
    """Return decomp-permuter's lowest-scoring output directory and its score."""

    candidates: list[tuple[int, Path]] = []
    for directory in scratch.glob("output-*"):
        if not directory.is_dir():
            continue
        parts = directory.name.split("-")
        if len(parts) >= 2 and parts[1].lstrip("-").isdigit():
            candidates.append((int(parts[1]), directory))
    if not candidates:
        return None, None
    candidates.sort(key=lambda pair: pair[0])
    return candidates[0][1], candidates[0][0]


def permuter_argv(
    *,
    python: str,
    permuter: Path,
    scratch: Path,
    threads: int,
    extra: Sequence[str] = (),
    nice: int | None = 15,
) -> list[str]:
    """Build the permuter command line, with the fidelity flags forced on.

    ``--stack-diffs`` is not optional. Without it the scorer normalizes
    stack offsets, and a spill at the wrong slot scores zero -- a "match"
    that does not rebuild.
    """

    argv: list[str] = []
    if nice is not None:
        argv += ["nice", "-n", str(nice)]
    argv += [
        python,
        str(permuter),
        "--stop-on-zero",
        "--quiet",
        "-j",
        str(threads),
    ]
    if "--stack-diffs" not in extra:
        argv.append("--stack-diffs")
    argv += [*extra, str(scratch)]
    return argv


def parse_base_score(log: str) -> int | None:
    match = BASE_SCORE_RE.search(log)
    return int(match.group(1)) if match else None


# ---------------------------------------------------------------------------
# Results
# ---------------------------------------------------------------------------


@dataclass
class SweepResult:
    """One function's outcome. Promotion is deliberately absent."""

    function: str
    source: str
    ok: bool = False
    base_score: int | None = None
    best_score: int | None = None
    zero_found: bool = False
    extended: bool = False
    flags: str | None = None
    flags_recovered: bool = False
    replicated_objcopy: int = 0
    skipped_postprocess: int = 0
    output_dir: str | None = None
    #: Where in the searched window the best candidate landed, 0.0 (first
    #: moment) to 1.0 (the last). This is the field that separates a search
    #: still descending when the clock stopped it from one that plateaued in
    #: its first minutes, and no other record of the run carries it: the
    #: output directories are the permuter's, and they are overwritten.
    best_output_mtime_fraction: float | None = None
    #: The wall-clock cap this search was given, in seconds, and whether it
    #: actually reached it. A run that stopped early stopped for a reason --
    #: score 0, or a crash -- and its timing means something different.
    window_seconds: float | None = None
    hit_cap: bool = False
    seconds: float = 0.0
    error: str | None = None
    warnings: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def sweep_payload(results: Sequence[SweepResult], *, final: bool) -> dict[str, Any]:
    return {
        "schema": SWEEP_SCHEMA,
        "final": final,
        "results": [result.as_dict() for result in results],
        "totals": {
            "run": len(results),
            "zero_found": sum(1 for result in results if result.zero_found),
            "extended": sum(1 for result in results if result.extended),
            "errored": sum(1 for result in results if result.error),
            "fallback_flags": sum(
                1 for result in results if result.ok and not result.flags_recovered
            ),
        },
    }


def completed_functions(summary: str | Path) -> set[str]:
    """Names already recorded in a summary, for ``--resume``."""

    path = Path(summary)
    if not path.is_file():
        return set()
    payload = json.loads(path.read_text(encoding="utf-8"))
    rows = payload.get("results", []) if isinstance(payload, dict) else []
    return {
        str(row["function"])
        for row in rows
        if isinstance(row, dict) and isinstance(row.get("function"), str)
    }


def earlier_results(summary: str | Path) -> list[SweepResult]:
    """Carry a previous sweep's rows forward so the summary stays whole."""

    path = Path(summary)
    if not path.is_file():
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    rows = payload.get("results", []) if isinstance(payload, dict) else []
    known = {item.name for item in fields(SweepResult)}
    carried: list[SweepResult] = []
    for row in rows:
        if isinstance(row, dict) and isinstance(row.get("function"), str):
            carried.append(SweepResult(**{k: v for k, v in row.items() if k in known}))
    return carried


def render_table(results: Sequence[SweepResult]) -> list[str]:
    header = (
        f"{'function':<32} {'base':>6} {'best':>6}  "
        f"{'zero':<5} {'ext':<4} {'flags':<9} {'time':>7}"
    )
    lines = [header]
    for result in results:
        lines.append(
            f"{result.function:<32} {result.base_score!s:>6} "
            f"{result.best_score!s:>6}  "
            f"{'yes' if result.zero_found else 'no':<5} "
            f"{'yes' if result.extended else 'no':<4} "
            f"{'real' if result.flags_recovered else 'FALLBACK':<9} "
            f"{result.seconds:>6.0f}s"
        )
    if results:
        total = len(results)
        zero = sum(1 for result in results if result.zero_found)
        errored = sum(1 for result in results if result.error)
        fallback = sum(
            1 for result in results if result.ok and not result.flags_recovered
        )
        lines.extend(
            (
                "",
                f"{total} run, {zero} reached score 0, {errored} errored, "
                f"{fallback} searched with fallback flags",
            )
        )
    return lines


def render_queue(items: Iterable[QueueItem]) -> list[str]:
    rows = list(items)
    lines = [f"{len(rows)} queued function(s):"]
    lines.extend(f"  {item.function}  ({item.source})" for item in rows)
    if not rows:
        lines.append("  nothing to do.")
    return lines


__all__ = [
    "CODEGEN_FLAG_RE",
    "DEFAULT_SKIP_POSTPROCESS",
    "DOCTOR_SCHEMA",
    "SWEEP_SCHEMA",
    "BuildRecipe",
    "QueueItem",
    "SweepResult",
    "append_compile_steps",
    "best_output",
    "completed_functions",
    "earlier_results",
    "join_continuations",
    "load_queue",
    "load_ranking",
    "object_target",
    "order_queue",
    "output_fraction",
    "parse_base_score",
    "parse_dry_run",
    "permuter_argv",
    "recipe_report",
    "recover_recipe",
    "render_queue",
    "render_settings",
    "render_table",
    "retarget_labels",
    "retarget_objcopy",
    "should_extend",
    "sweep_payload",
    "wait_for_headroom",
]
