"""The colour landscape at any order: probe every web against a held force set.

Every force grid `oracle` builds is first-order: each web is probed against
the *unforced* baseline. On Mickey's Speedway USA's largest function (a
14 KB overlay procedure, 2026-09-14..16) that was the wall. Five forces were
known good; the question that remained was what every *other* web does once
those five are held -- and twelve productive forces, three of them never
nominated by any first-order landscape, were invisible until a campaign tool
kept a packed set applied while probing the rest. The third-order landscape
then found nothing, which was the first closure of the colour axis anybody
could state.

The procedure, which this module makes a contract rather than a script:

1. **Hold.** Compile the baseline with the held forces applied and read the
   probe plan from *that baseline's own trace*. Held colours change which
   colours every other web is offered and what each costs, so a plan read
   off an unforced trace is a plan for a different allocation. A caller who
   supplies a trace alongside a hold is refused for that reason.
2. **Probe.** Every coloured phase-one web other than a held one, at one
   legal colour (or every legal colour), with the held set added to the
   cell. The legal colours are the web's own `p1cost` table, not its
   `available0/1` mask: the mask is the state at the moment the web was
   decided and a force overrides the decision, so it under-reports. Probes
   stay inside the web's save kind where they can, because a caller-save
   colour on a callee-save web rewrites the prologue, moves the size, and
   the cell has to be thrown away.
3. **Footprint.** Each cell's masked positional mismatches, bucketed into
   fixed windows, minus the held baseline's. Both objects are compared with
   the same target, so an insertion's positional shadow cancels in the
   difference -- unless the cell itself changed the size, and those cells are
   reported and excluded rather than mapped.
4. **Pack.** The best *set* of forces is a maximum-gain packing over those
   footprints (their radii): no two members may share a window, and a web
   has one colour. Sorting winners by score gets this wrong measurably -- a
   force that scores better alone can duplicate another member's radius and
   abandon a region only a worse-scoring colour reaches.

The packing is a prediction. Disjoint radii implied additivity on every pair
measured in the campaign, but they do not guarantee it, and the report says
to measure the packed set before holding it.

Only phase one is landscaped. Phase two assigns in ascending web number with
the lowest free colour, so moving one p2 web re-decides every later one and a
footprint no longer belongs to the web that was probed.

Nothing here is a source match. A forced object is a statement about the
allocator; the report carries that sentence and the claim is structural in
:mod:`decomp_workbench.provenance`.
"""

from __future__ import annotations

import hashlib
import itertools
import os
import tempfile
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .campaign import (
    ParameterizedCandidate,
    render_compile_command,
    run_compiler,
    run_parameterized_campaign,
)
from .compare import compare_objects
from .globalcolor import (
    GlobalColorTrace,
    optional_integer,
    parse_globalcolor_trace,
    register_for_color,
)
from .instrument_uopt import parse_force_specification
from .model import CompileResult

__all__ = [
    "DEFAULT_WINDOW",
    "LANDSCAPE_SCHEMA",
    "MAX_PACKED_WINNERS",
    "LandscapeWeb",
    "Probe",
    "footprint",
    "histogram",
    "landscape_report",
    "landscape_webs",
    "mismatch_positions",
    "pack",
    "plan_probes",
    "rivals",
    "run_landscape",
    "validate_hold",
    "winners",
]

LANDSCAPE_SCHEMA = "decomp-workbench-landscape-v1"

#: Window width in bytes. `0x80` is the width at which every pair of the
#: campaign's measured lattice read disjoint and measured additive; at `0x200`
#: two forces near the entry shared a window without interacting. A
#: collision at a coarse width is a question for a narrower one.
DEFAULT_WINDOW = 0x80

#: The packing is exact by branch and bound over the winners. The largest
#: function in the originating campaign produced twelve; a list longer than
#: this is packed over its best members and the report says so.
MAX_PACKED_WINNERS = 24

#: Tracing controls the landscape sets on the held baseline's capture.
TRACE_ENVIRONMENT = ("CDX_LOG", "CDX_OUT", "CDX_DETAIL_WEB")

PROOF = (
    "Compiler-decision probes only. A forced object is never source-match "
    "evidence; a winner is a force to add to the held set, and the packing "
    "is a prediction to measure before holding it."
)


@dataclass(frozen=True)
class LandscapeWeb:
    """One coloured phase-one web, as its own trace records it."""

    web: int
    color: int
    register: str | None
    costs: Mapping[int, float]
    kinds: Mapping[int, str | None]

    @property
    def kind(self) -> str | None:
        return self.kinds.get(self.color)

    def legal_colors(self, *, same_kind: bool) -> list[int]:
        """Every colour in the web's own cost table other than its own."""

        return [
            color
            for color in self.costs
            if color != self.color
            and (not same_kind or self.kinds.get(color) == self.kind)
        ]


@dataclass(frozen=True)
class Probe:
    """One planned cell: a web and the colour it is forced to, or why not."""

    web: int
    color: int | None
    reason: str = ""

    @property
    def force(self) -> str | None:
        return None if self.color is None else f"p1:w{self.web}=c{self.color}"


def landscape_webs(trace: GlobalColorTrace, *, proc: int) -> dict[int, LandscapeWeb]:
    """Read every coloured phase-one web of one procedure.

    A web is coloured when it has a `p1color` record. Its legal colours are the
    keys of its `p1cost` records and `kind=` separates caller- from callee-save
    (L157 in the originating campaign's numbering).
    """

    colors: dict[int, tuple[int, str | None]] = {}
    costs: dict[int, dict[int, float]] = {}
    kinds: dict[int, dict[int, str | None]] = {}
    for item in trace.decisions:
        if optional_integer(item.fields.get("proc")) != proc:
            continue
        web = optional_integer(item.fields.get("web"))
        color = optional_integer(item.fields.get("color"))
        if web is None or color is None:
            continue
        if item.phase == "p1color":
            register = item.fields.get("reg")
            colors[web] = (
                color,
                register if register not in {None, "?", "-"} else None,
            )
        elif item.phase == "p1cost":
            try:
                cost = float(item.fields.get("cost", "nan"))
            except ValueError:
                continue
            costs.setdefault(web, {})[color] = cost
            kinds.setdefault(web, {})[color] = item.fields.get("kind")
    return {
        web: LandscapeWeb(
            web=web,
            color=color,
            register=register or register_for_color(color),
            costs=dict(costs.get(web, {})),
            kinds=dict(kinds.get(web, {})),
        )
        for web, (color, register) in sorted(colors.items())
    }


def validate_hold(hold: Iterable[str]) -> tuple[str, ...]:
    """Parse and normalise a hold list; one force per web, phase qualified."""

    entries = [entry for text in hold for entry in parse_force_specification(text)]
    seen: set[tuple[str, int]] = set()
    for entry in entries:
        key = (entry.phase, entry.web)
        if key in seen:
            raise ValueError(
                f"the hold names {entry.phase}:w{entry.web} twice; a web has one colour"
            )
        seen.add(key)
    return tuple(str(entry) for entry in entries)


def _held_webs(hold: Sequence[str]) -> set[int]:
    return {
        entry.web
        for text in hold
        for entry in parse_force_specification(text)
        if entry.phase == "p1"
    }


def _probe_color(entry: LandscapeWeb, *, cross_kind: bool) -> int | None:
    """The smallest legal perturbation that still relocates the web."""

    legal = entry.legal_colors(same_kind=False)
    if not cross_kind:
        same = entry.legal_colors(same_kind=True)
        legal = same or legal
    if not legal:
        return None
    return min(
        legal,
        key=lambda color: (
            entry.kinds.get(color) != entry.kind,
            entry.costs[color],
            abs(color - entry.color),
            color,
        ),
    )


def plan_probes(
    webs: Mapping[int, LandscapeWeb],
    *,
    hold: Sequence[str] = (),
    every_colour: bool = False,
    cross_kind: bool = False,
    wanted: Sequence[int] | None = None,
) -> list[Probe]:
    """Return the cells to compile, in order.

    A held web is not planned: its colour is the premise of the landscape.
    A requested web the trace does not colour is kept as a probe with no
    colour and a reason, so a typo is visible rather than silently dropped.
    """

    pinned = _held_webs(hold)
    order = list(wanted) if wanted else sorted(webs)
    plan: list[Probe] = []
    for web in order:
        if web in pinned:
            continue
        entry = webs.get(web)
        if entry is None:
            plan.append(Probe(web, None, "no p1color record for this web"))
            continue
        if every_colour:
            colours = sorted(
                entry.legal_colors(same_kind=not cross_kind),
                key=lambda color: (abs(color - entry.color), color),
            )
            if colours:
                plan.extend(Probe(web, color) for color in colours)
            else:
                plan.append(
                    Probe(web, None, "no other same-kind colour in its cost table")
                )
            continue
        color = _probe_color(entry, cross_kind=cross_kind)
        plan.append(
            Probe(web, color)
            if color is not None
            else Probe(web, None, "no second colour in its cost table")
        )
    return plan


def mismatch_positions(result: CompileResult) -> list[int] | None:
    """Masked positional mismatch indices of one compiled cell, or None."""

    comparison = result.comparison
    if comparison is None:
        return None
    return sorted(
        int(site["index"])
        for site in comparison.diff_sites
        if site.get("class") != "relocation-controlled"
    )


def histogram(positions: Iterable[int], width: int) -> dict[int, int]:
    """Bucket word indices into byte windows of `width`."""

    counts: dict[int, int] = {}
    for index in positions:
        key = (index * 4) // width * width
        counts[key] = counts.get(key, 0) + 1
    return counts


def footprint(base: Mapping[int, int], cell: Mapping[int, int]) -> dict[int, int]:
    """The signed per-window change a cell makes against its baseline."""

    moved = {key: cell.get(key, 0) - base.get(key, 0) for key in set(base) | set(cell)}
    return {key: value for key, value in sorted(moved.items()) if value}


def _windows(row: Mapping[str, Any]) -> dict[int, int]:
    """A row's footprint with integer keys, whether fresh or reloaded from JSON."""

    return {
        int(key, 0) if isinstance(key, str) else int(key): int(value)
        for key, value in (row.get("footprint") or {}).items()
    }


def winners(rows: Sequence[Mapping[str, Any]], base_score: int) -> list[dict[str, Any]]:
    """Probes that beat the held baseline without changing the size."""

    return sorted(
        (
            dict(row)
            for row in rows
            if row.get("status") == "ok"
            and isinstance(row.get("score"), int)
            and row["score"] < base_score
        ),
        key=lambda row: (row["score"], row["web"], row.get("color") or 0),
    )


def rivals(
    rows: Sequence[Mapping[str, Any]], base_score: int
) -> list[list[dict[str, Any]]]:
    """Winning forces that share one radius exactly: one question, many handles."""

    groups: dict[frozenset[int], list[dict[str, Any]]] = {}
    for row in winners(rows, base_score):
        groups.setdefault(frozenset(_windows(row)), []).append(row)
    return [
        sorted(group, key=lambda row: (row["score"], row["web"]))
        for _, group in sorted(groups.items(), key=lambda item: sorted(item[0]))
        if len(group) > 1
    ]


def pack(
    rows: Sequence[Mapping[str, Any]],
    base_score: int,
    *,
    limit: int = MAX_PACKED_WINNERS,
) -> dict[str, Any]:
    """The best set of winners whose radii do not overlap, one colour per web.

    Exact by branch and bound. A radius is the set of windows a force moves;
    a winner with an empty radius cannot be packed (it changed the score but
    no window, which only a masked-relocation artefact can do) and is left
    out rather than admitted as free.
    """

    candidates = [row for row in winners(rows, base_score) if _windows(row)]
    truncated = len(candidates) > limit
    candidates = candidates[:limit]
    gains = [base_score - int(row["score"]) for row in candidates]
    radii = [frozenset(_windows(row)) for row in candidates]
    suffix = [*list(itertools.accumulate(reversed(gains)))[::-1], 0]
    best: list[int] = []
    best_gain = 0

    def search(
        index: int,
        chosen: list[int],
        covered: frozenset[int],
        webs: frozenset[int],
        gain: int,
    ) -> None:
        nonlocal best, best_gain
        if gain > best_gain:
            best, best_gain = list(chosen), gain
        if index >= len(candidates) or gain + suffix[index] <= best_gain:
            return
        row = candidates[index]
        if not (covered & radii[index]) and row["web"] not in webs:
            chosen.append(index)
            search(
                index + 1,
                chosen,
                covered | radii[index],
                webs | {row["web"]},
                gain + gains[index],
            )
            chosen.pop()
        search(index + 1, chosen, covered, webs, gain)

    search(0, [], frozenset(), frozenset(), 0)
    members = [candidates[index] for index in best]
    return {
        "forces": [str(row["force"]) for row in members],
        "members": [
            {
                "force": row["force"],
                "web": row["web"],
                "color": row.get("color"),
                "register": row.get("register"),
                "score": row["score"],
                "gain": base_score - int(row["score"]),
                "radius": [f"{window:#x}" for window in sorted(_windows(row))],
            }
            for row in members
        ],
        "predicted_score": base_score - best_gain,
        "predicted_gain": best_gain,
        "winners_considered": len(candidates),
        "truncated": truncated,
        "rule": (
            "maximum total gain over winners whose radii share no window, at "
            "most one colour per web; a prediction that assumes additivity, "
            "which disjoint radii imply but do not guarantee"
        ),
    }


def _row_payload(row: Mapping[str, Any]) -> dict[str, Any]:
    payload = dict(row)
    payload["footprint"] = {
        f"{window:#x}": value for window, value in sorted(_windows(row).items())
    }
    return payload


def landscape_report(
    rows: Sequence[Mapping[str, Any]],
    *,
    base_score: int | None,
    hold: Sequence[str],
    window: int,
    proc: int,
    planned: int,
    trace_identity: str | None = None,
    baseline: Mapping[str, Any] | None = None,
    warnings: Sequence[str] = (),
    inputs: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Assemble the versioned landscape document from measured rows."""

    ok = [row for row in rows if row.get("status") == "ok"]
    located = [row for row in ok if _windows(row)]
    silent = [row for row in ok if not _windows(row)]
    size_moved = [row for row in rows if row.get("status") == "size-changed"]
    not_probed = [row for row in rows if row.get("status") in {"not-probed", "failed"}]
    found = winners(rows, base_score) if base_score is not None else []
    packing = pack(rows, base_score) if base_score is not None else None
    held = list(hold)
    closure = None
    if base_score is not None and ok and not found:
        closure = (
            f"no single probe beat the {'held' if held else 'unforced'} "
            f"baseline ({base_score}) at delta 0 over {len(ok)} measured "
            f"probe(s) of {len({row['web'] for row in ok})} web(s): "
            + (
                "this hold set is a floor for any one additional force"
                if held
                else "no single force improves this body"
            )
            + " -- scoped to these probes and this source hash, never a claim "
            "that no source reaches the target"
        )
    index: dict[int, list[tuple[int, str]]] = {}
    for row in located:
        for window_key, moved in _windows(row).items():
            index.setdefault(window_key, []).append((abs(moved), str(row["force"])))
    nomination = [
        {
            "window": f"{window_key:#x}",
            "forces": [
                force
                for _, force in sorted(entries, key=lambda item: (-item[0], item[1]))
            ],
        }
        for window_key, entries in sorted(index.items())
    ]
    next_hold = (
        held + list(packing["forces"]) if packing and packing["forces"] else None
    )
    return {
        "schema": LANDSCAPE_SCHEMA,
        "evidence": "diagnostic-colour-landscape",
        "order": "held" if held else "first",
        "procedure": proc,
        "hold": held,
        "window": window,
        "baseline": dict(baseline) if baseline is not None else None,
        "base_score": base_score,
        "trace_identity": trace_identity,
        "planned_probes": planned,
        "measured_probes": len(ok),
        "located": len(located),
        "moved_nothing": [row["force"] for row in silent],
        "size_changed": [row["force"] for row in size_moved],
        "not_probed": [
            {"web": row["web"], "force": row.get("force"), "reason": row.get("reason")}
            for row in not_probed
        ],
        "rows": [_row_payload(row) for row in rows],
        "winners": [
            {
                "force": row["force"],
                "score": row["score"],
                "gain": base_score - int(row["score"])
                if base_score is not None
                else None,
            }
            for row in found
        ],
        "rivals": [
            [row["force"] for row in group] for group in rivals(rows, base_score)
        ]
        if base_score is not None
        else [],
        "packing": packing,
        "next_hold": next_hold,
        "closure": closure,
        "nomination": nomination,
        "inputs": dict(inputs) if inputs is not None else None,
        "warnings": list(warnings),
        "proof": PROOF,
    }


# -- running one ---------------------------------------------------------


@dataclass
class _Capture:
    trace: GlobalColorTrace
    object_sha256: str | None
    path: Path


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def capture_held_trace(
    *,
    source: Path,
    template: str,
    environment: Mapping[str, str],
    proc: int,
    hold: Sequence[str],
    trace_path: Path,
    compile_cwd: Path,
    timeout: float | None,
    fingerprint: Callable[[Path], str | None] | None = None,
    runner: Callable[..., Any] = run_compiler,
) -> _Capture:
    """Compile the held baseline once with tracing on and read its trace.

    The object is retained only long enough to fingerprint it: the scored
    baseline is compiled again with tracing off, and the two function
    fingerprints are the evidence that tracing did not change what the plan was
    read from. `fingerprint` must hash the function the same way the
    comparison does; without one the identity is not checked.
    """

    trace_path.parent.mkdir(parents=True, exist_ok=True)
    if trace_path.exists():
        trace_path.unlink()
    capture_env = {
        **environment,
        "CDX_LOG": "1",
        "CDX_DETAIL_WEB": "all",
        "CDX_OUT": str(trace_path),
        "CDX_PROC": str(proc),
    }
    if hold:
        capture_env["CDX_FORCE"] = ",".join(hold)
    with tempfile.TemporaryDirectory(prefix="dkwb-landscape-") as scratch:
        output = Path(scratch) / "held-baseline.o"
        command = render_compile_command(template, source, output)
        completed = runner(
            command,
            environment=dict(capture_env),
            compile_cwd=compile_cwd,
            timeout=timeout,
        )
        if completed.returncode != 0:
            raise RuntimeError(
                "the traced held baseline failed to compile "
                f"(exit {completed.returncode}): {completed.stderr[-2048:]}"
            )
        digest = (
            fingerprint(output)
            if fingerprint is not None and output.is_file()
            else None
        )
    if not trace_path.is_file():
        raise RuntimeError(
            f"the traced held baseline wrote no trace to {trace_path}; the "
            "compiler must be the instrumented uopt, and it writes the log to "
            "CDX_OUT (CDX_LOG=1 alone writes nothing)"
        )
    text = trace_path.read_text(encoding="utf-8", errors="replace")
    return _Capture(
        trace=parse_globalcolor_trace(text), object_sha256=digest, path=trace_path
    )


@dataclass
class LandscapeRun:
    """Everything a landscape run needs beyond its inputs' identity."""

    source: Path
    target: Path
    template: str
    environment: dict[str, str]
    cache_dir: Path
    state_dir: Path
    proc: int
    hold: tuple[str, ...] = ()
    trace: Path | None = None
    every_colour: bool = False
    cross_kind: bool = False
    webs: tuple[int, ...] = ()
    limit: int = 0
    window: int = DEFAULT_WINDOW
    jobs: int = 1
    objdump: str | None = None
    symbol: str | None = None
    section: str = ".text"
    compile_cwd: Path = field(default_factory=Path.cwd)
    timeout: float | None = 120.0


def run_landscape(
    run: LandscapeRun,
    *,
    compiler: Callable[..., Any] = run_compiler,
    campaign: Callable[..., list[CompileResult]] = run_parameterized_campaign,
) -> dict[str, Any]:
    """Capture, plan, compile and read one landscape; return its report."""

    if run.window <= 0 or run.window % 4:
        raise ValueError("--window must be a positive multiple of 4 bytes")
    hold = validate_hold(run.hold)
    if hold and run.trace is not None:
        raise ValueError(
            "--trace cannot be combined with --hold: the held baseline's own "
            "trace is the one whose cost tables the probes are planned from, "
            "and an unforced trace plans against the wrong tables"
        )
    for name in ("CDX_FORCE", "CDX_PROC", *TRACE_ENVIRONMENT):
        if name in run.environment:
            raise ValueError(
                f"the landscape owns {name}; remove it from --env (use --hold "
                "for forces and --proc for the procedure)"
            )

    warnings: list[str] = []
    trace_identity: str | None = None
    capture_sha: str | None = None
    if run.trace is not None:
        text = run.trace.read_text(encoding="utf-8", errors="replace")
        trace = parse_globalcolor_trace(text)
        trace_identity = "supplied"
        warnings.append(
            "the probe plan was read from a supplied trace; its identity with "
            "the scored baseline was not checked"
        )
    else:
        capture = capture_held_trace(
            source=run.source,
            template=run.template,
            environment=run.environment,
            proc=run.proc,
            hold=hold,
            trace_path=run.state_dir / "held-baseline.cdx.log",
            compile_cwd=run.compile_cwd,
            timeout=run.timeout,
            fingerprint=lambda path: (
                compare_objects(
                    run.target,
                    path,
                    objdump=run.objdump,
                    symbol=run.symbol,
                    section=run.section,
                ).candidate_sha256
            ),
            runner=compiler,
        )
        trace = capture.trace
        capture_sha = capture.object_sha256

    webs = landscape_webs(trace, proc=run.proc)
    if not webs:
        raise ValueError(
            f"the trace records no coloured phase-one web for proc={run.proc}; "
            "check --proc (the ordinal, not the name) and that the capture "
            "carried CDX_DETAIL_WEB=all"
        )
    held_missing = sorted(_held_webs(hold) - set(webs))
    if held_missing:
        warnings.append(
            "held web(s) "
            + ", ".join(f"w{web}" for web in held_missing)
            + " have no p1color record in the held trace; the hold may not "
            "have applied"
        )
    plan = plan_probes(
        webs,
        hold=hold,
        every_colour=run.every_colour,
        cross_kind=run.cross_kind,
        wanted=run.webs or None,
    )
    if run.limit:
        plan = plan[: run.limit]

    base_env = {**run.environment, "CDX_PROC": str(run.proc)}
    if hold:
        base_env["CDX_FORCE"] = ",".join(hold)
    variants = [
        ParameterizedCandidate(
            source=run.source,
            environment=dict(base_env),
            metadata={"schema": LANDSCAPE_SCHEMA, "baseline": True},
        )
    ]
    for probe in plan:
        if probe.color is None:
            continue
        variants.append(
            ParameterizedCandidate(
                source=run.source,
                environment={
                    **run.environment,
                    "CDX_PROC": str(run.proc),
                    "CDX_FORCE": ",".join((*hold, str(probe.force))),
                },
                metadata={
                    "schema": LANDSCAPE_SCHEMA,
                    "baseline": False,
                    "force": probe.force,
                    "web": probe.web,
                    "color": probe.color,
                },
            )
        )
    results = campaign(
        variants,
        target=run.target,
        template=run.template,
        cache_dir=run.cache_dir,
        ledger=run.state_dir / "ledger.jsonl",
        jobs=run.jobs,
        objdump=run.objdump,
        symbol=run.symbol,
        section=run.section,
        compile_cwd=run.compile_cwd,
        stop_on_exact=False,
        timeout=run.timeout,
    )
    by_force: dict[str | None, CompileResult] = {}
    baseline_result: CompileResult | None = None
    for result in results:
        metadata = result.experiment if isinstance(result.experiment, dict) else {}
        if metadata.get("baseline"):
            baseline_result = result
        else:
            by_force[metadata.get("force")] = result
    if baseline_result is None or baseline_result.comparison is None:
        raise RuntimeError(
            "the held baseline failed to compile or compare; nothing can be "
            "differenced against it"
        )
    base = baseline_result.comparison
    base_positions = mismatch_positions(baseline_result) or []
    base_hist = histogram(base_positions, run.window)
    base_score = base.word_mismatches
    if capture_sha is not None:
        trace_identity = (
            "identical" if capture_sha == base.candidate_sha256 else "differs"
        )
        if trace_identity == "differs":
            warnings.append(
                "the traced held baseline and the scored held baseline are "
                "different objects: tracing changed code generation, so the "
                "plan describes an allocation that was not scored. Gate the "
                "instrumented compiler before trusting this landscape"
            )
    if run.every_colour and base.instruction_delta:
        raise ValueError(
            f"refusing --every-colour: the held baseline differs from the "
            f"target in size ({base.instruction_delta:+d} instruction(s)); a "
            "colour landscape on a size mismatch maps insertion shadow, not "
            "webs. Close the size first"
        )
    if base.instruction_delta:
        warnings.append(
            f"the held baseline is {base.instruction_delta:+d} instruction(s) "
            "from the target's size; every footprint is read through an "
            "insertion shadow"
        )
    elif base.aligned_structural:
        warnings.append(
            f"the held baseline is the target's size but aligns with "
            f"{base.aligned_structural} structural row(s): insertion pairs "
            "that cancel in size. No colour moves them, and a landscape "
            "floor here is partly unreachable by any force"
        )

    rows: list[dict[str, Any]] = []
    for probe in plan:
        entry = webs.get(probe.web)
        row: dict[str, Any] = {
            "web": probe.web,
            "color": probe.color,
            "force": probe.force,
            "register": register_for_color(probe.color)
            if probe.color is not None
            else None,
            "held_register": entry.register if entry else None,
            "score": None,
            "footprint": {},
            "status": "not-probed",
            "reason": probe.reason or None,
        }
        if probe.color is None:
            rows.append(row)
            continue
        cell = by_force.get(probe.force)
        comparison = cell.comparison if cell is not None else None
        if cell is None or comparison is None:
            row["status"] = "failed"
            row["reason"] = (
                f"compile or comparison failed (exit "
                f"{cell.returncode if cell is not None else '?'})"
            )
            rows.append(row)
            continue
        row["score"] = comparison.word_mismatches
        size_delta = comparison.instruction_delta - base.instruction_delta
        if size_delta:
            row["status"] = "size-changed"
            row["reason"] = (
                f"size {size_delta:+d} instruction(s) against the held "
                "baseline; the insertion shadow shifts and cannot be "
                "differenced"
            )
        else:
            row["status"] = "ok"
            row["footprint"] = footprint(
                base_hist, histogram(mismatch_positions(cell) or [], run.window)
            )
            if comparison.candidate_sha256 == base.candidate_sha256:
                row["reason"] = "object identical to the held baseline"
        rows.append(row)

    return landscape_report(
        rows,
        base_score=base_score,
        hold=hold,
        window=run.window,
        proc=run.proc,
        planned=len(plan),
        trace_identity=trace_identity,
        baseline={
            "score": base_score,
            "instruction_delta": base.instruction_delta,
            "aligned_structural": base.aligned_structural,
            "object_sha256": base.candidate_sha256,
        },
        warnings=warnings,
        inputs={
            "source": {"path": str(run.source), "sha256": _sha256(run.source)},
            "target": {"path": str(run.target), "sha256": _sha256(run.target)},
            "compile_command": run.template,
            "environment": dict(sorted(run.environment.items())),
            "every_colour": run.every_colour,
            "cross_kind": run.cross_kind,
            "symbol": run.symbol,
            "section": run.section,
        },
    )


def freshness(report: Mapping[str, Any], *, source: Path | None = None) -> str | None:
    """Say plainly when a saved landscape no longer describes its source.

    A landscape is measured against one function body; a source change voids
    it. Five consecutive campaign lanes measured colours against a body that
    had moved underneath them before this became a line of output.
    """

    inputs = report.get("inputs")
    recorded = inputs.get("source") if isinstance(inputs, dict) else None
    if not isinstance(recorded, dict) or not recorded.get("sha256"):
        return (
            "this landscape carries no source fingerprint, so whether it still "
            "describes the tree cannot be checked -- re-run it"
        )
    path = source or (Path(recorded["path"]) if recorded.get("path") else None)
    if path is None or not path.is_file():
        return None
    current = _sha256(path)
    if current != recorded["sha256"]:
        return (
            f"STALE: measured against source {recorded['sha256'][:12]}, "
            f"{path.name} is now {current[:12]}. A source change voids a "
            "landscape; re-run it before nominating from it"
        )
    return None


def repack(report: Mapping[str, Any]) -> dict[str, Any]:
    """Recompute winners, rivals and the packing from a saved report's rows."""

    rows = [dict(row) for row in report.get("rows", []) if isinstance(row, dict)]
    return landscape_report(
        rows,
        base_score=report.get("base_score"),
        hold=list(report.get("hold") or []),
        window=int(report.get("window") or DEFAULT_WINDOW),
        proc=int(report.get("procedure") or 0),
        planned=int(report.get("planned_probes") or len(rows)),
        trace_identity=report.get("trace_identity"),
        baseline=report.get("baseline"),
        warnings=list(report.get("warnings") or []),
        inputs=report.get("inputs"),
    )


def state_directory(
    root: Path, *, source: Path, hold: Sequence[str], proc: int
) -> Path:
    """Where one landscape's trace, ledger and report live."""

    digest = hashlib.sha256(
        "\0".join((str(source), _sha256(source), str(proc), *hold)).encode("utf-8")
    ).hexdigest()[:12]
    stem = "".join(ch if ch.isalnum() else "-" for ch in source.stem).strip("-")
    return root / "landscape" / f"{stem[:40] or 'source'}-{digest}"


def write_report(path: Path, report: Mapping[str, Any]) -> None:
    """Write the report atomically inside its own state directory."""

    import json

    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", "utf-8")
    os.replace(temporary, path)
