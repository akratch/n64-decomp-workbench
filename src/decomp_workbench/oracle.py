"""Calibrated allocator-oracle planning and semantic trace comparison."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from .allocator_analysis import compare_semantic_webs, semantic_webs
from .artifacts import DEFAULT_STREAM_LIMIT
from .campaign import ParameterizedCandidate, run_parameterized_campaign
from .compare import compare_objects
from .globalcolor import (
    GlobalColorTrace,
    optional_integer,
    register_for_color,
)
from .model import CompileResult

PLAN_SCHEMA = "decomp-workbench-oracle-plan-v1"
DIFF_SCHEMA = "decomp-workbench-oracle-diff-v1"
SWEEP_SCHEMA = "decomp-workbench-oracle-sweep-v1"
EFFECT_SCHEMA = "decomp-workbench-oracle-emitted-effect-v1"
PHASES = ("p1", "p2")


def _selected_proc(trace: GlobalColorTrace, proc: int | None) -> int:
    procedures = sorted(
        {
            value
            for item in trace.decisions
            if item.phase in {"p1dec", "p2dec"}
            if (value := optional_integer(item.fields.get("proc"))) is not None
        }
    )
    if proc is not None:
        if proc not in procedures:
            rendered = ", ".join(str(item) for item in procedures) or "none"
            raise ValueError(
                f"procedure {proc} has no allocator decisions; available: {rendered}"
            )
        return proc
    if len(procedures) != 1:
        rendered = ", ".join(str(item) for item in procedures) or "none"
        raise ValueError(
            "oracle planning requires --proc when the trace does not contain "
            f"exactly one procedure; available: {rendered}"
        )
    return procedures[0]


def _observed_colors(
    trace: GlobalColorTrace,
    *,
    proc: int,
) -> dict[str, set[int]]:
    colors: dict[str, set[int]] = defaultdict(set)
    for item in trace.decisions:
        phase = item.phase[:2]
        if phase not in PHASES:
            continue
        if optional_integer(item.fields.get("proc")) != proc:
            continue
        if item.phase in {"p1cost", "p2cost"}:
            color = optional_integer(item.fields.get("color"))
            if color is not None and color >= 0:
                colors[phase].add(color)
    return colors


def oracle_plan(
    trace: GlobalColorTrace,
    *,
    proc: int | None = None,
    colors: Mapping[str, Sequence[int]] | None = None,
    include_split: bool = True,
) -> dict[str, Any]:
    """Build a phase-complete grid from recorded decisions and viable colors.

    Color candidates come from explicit overrides or measured cost records.
    Assigned colors are deliberately not widened into a guessed register
    universe: an incomplete but honest plan is safer than a fake exhaustive
    sweep.
    """

    selected_proc = _selected_proc(trace, proc)
    observed = _observed_colors(trace, proc=selected_proc)
    overrides = {phase: set(values) for phase, values in (colors or {}).items()}
    unknown = sorted(set(overrides) - set(PHASES))
    if unknown:
        raise ValueError("unknown allocator phase(s): " + ", ".join(unknown))
    phase_colors = {
        phase: sorted(overrides.get(phase, observed.get(phase, set())))
        for phase in PHASES
    }
    for phase, values in phase_colors.items():
        if any(color < 0 or color > 63 for color in values):
            raise ValueError(f"{phase} colors must be in the mask range c0..c63")

    decisions = {}
    for decision in trace.allocator_webs(proc=selected_proc):
        key = (decision.phase_tag, decision.web)
        if key in decisions:
            raise ValueError(
                "trace repeats allocator decision "
                f"{decision.phase_tag}:w{decision.web}; "
                "use one invocation per oracle plan"
            )
        decisions[key] = decision
    attributions = {
        (web.decision.phase_tag, web.decision.web): web.source_attribution
        for web in semantic_webs(trace, proc=selected_proc)
    }

    forces: list[dict[str, Any]] = []
    coverage: dict[str, dict[str, Any]] = {}
    for phase in PHASES:
        phase_webs = [web for (tag, _), web in decisions.items() if tag == phase]
        phase_webs.sort(key=lambda item: item.web)
        count_before = len(forces)
        for web in phase_webs:
            attribution = attributions.get(
                (web.phase_tag, web.web),
                {"classification": "run-local-unattributed"},
            )
            for color in phase_colors[phase]:
                if color in web.forbidden_colors:
                    continue
                forces.append(
                    {
                        "force": f"{phase}:w{web.web}=c{color}",
                        "phase": phase,
                        "web": web.web,
                        "color": color,
                        "register": register_for_color(color),
                        "decision": web.fields.get("decision"),
                        "source_attribution": attribution,
                        "source": {
                            key: web.detail[key]
                            for key in ("file", "line", "source", "expr", "listing")
                            if web.detail.get(key)
                        },
                    }
                )
            if include_split:
                forces.append(
                    {
                        "force": f"{phase}:w{web.web}=s",
                        "phase": phase,
                        "web": web.web,
                        "color": None,
                        "register": None,
                        "decision": web.fields.get("decision"),
                        "source_attribution": attribution,
                        "source": {
                            key: web.detail[key]
                            for key in ("file", "line", "source", "expr", "listing")
                            if web.detail.get(key)
                        },
                    }
                )
        coverage[phase] = {
            "webs": len(phase_webs),
            "colors": phase_colors[phase],
            "include_split": include_split,
            "forces": len(forces) - count_before,
            "color_source": (
                "override" if phase in overrides else "measured-cost-records"
            ),
        }

    semantic = semantic_webs(trace, proc=selected_proc)
    source_experiment_recommendations = [
        {
            "force_key": web.decision.force_key,
            "source_semantic": web.source_attribution["source_semantic"],
            "recommendation": (
                "Use this direct source semantic handle to design a source "
                "lifetime, priority, or coalescing experiment."
            ),
        }
        for web in semantic
        if web.source_attribution["classification"] == "source-attributed"
    ]
    unattributed_webs = sum(
        web.source_attribution["classification"] == "run-local-unattributed"
        for web in semantic
    )
    warnings = []
    for phase in PHASES:
        if coverage[phase]["webs"] == 0:
            warnings.append(f"{phase}: 0 allocator webs recorded")
        elif not phase_colors[phase] and not include_split:
            warnings.append(
                f"{phase}: no measured colors; pass an explicit {phase} color set"
            )
    return {
        "schema": PLAN_SCHEMA,
        "evidence": "diagnostic-oracle-plan",
        "procedure": selected_proc,
        "coverage": coverage,
        "both_phases_reported": set(coverage) == set(PHASES),
        "forces": forces,
        "force_count": len(forces),
        "source_attribution": {
            "classification": (
                "source-attributed"
                if not unattributed_webs
                else "mixed"
                if source_experiment_recommendations
                else "run-local-unattributed"
            ),
            "source_attributed_webs": len(source_experiment_recommendations),
            "run_local_unattributed_webs": unattributed_webs,
            "source_experiment_recommendations": source_experiment_recommendations,
            "next_gate": (
                None
                if source_experiment_recommendations
                else "Record a direct source_semantic for the allocator web; "
                "web, color, owner, lineage, and line fields remain run-local "
                "and do not support a source-experiment recommendation."
            ),
        },
        "warnings": warnings,
        "proof": (
            "Compiler-decision probes only. Forbidden colors are omitted; both "
            "phase namespaces are always reported, including zero-web phases."
        ),
    }


def oracle_diff(
    target: GlobalColorTrace,
    candidate: GlobalColorTrace,
    *,
    proc: int | None = None,
) -> dict[str, Any]:
    """Compare two allocator traces through stable semantic fingerprints."""

    semantic = compare_semantic_webs(target, candidate, proc=proc)
    return {
        "schema": DIFF_SCHEMA,
        "evidence": "diagnostic-oracle-diff",
        "semantic": semantic,
        "difference_count": semantic["difference_count"],
        "proof": (
            "Compiler-decision evidence aligned by semantic provenance. Numeric "
            "web IDs and forced objects are never source-match evidence."
        ),
    }


def _compact_result(result: CompileResult) -> dict[str, Any]:
    metadata = result.experiment if isinstance(result.experiment, dict) else {}
    comparison = result.comparison
    compact_comparison = None
    if comparison is not None:
        compact_comparison = {
            "exact": comparison.exact,
            "verdict": comparison.verdict,
            "aligned_total": comparison.aligned_total,
            "aligned_structural": comparison.aligned_structural,
            "aligned_schedule": comparison.aligned_schedule,
            "aligned_register": comparison.aligned_register,
            "aligned_constant": comparison.aligned_constant,
            "words": comparison.word_mismatches,
            "candidate_instructions": comparison.candidate_instructions,
            "target_instructions": comparison.target_instructions,
            "candidate_sha256": comparison.candidate_sha256,
        }
    return {
        "force": metadata.get("force"),
        "phase": metadata.get("phase"),
        "web": metadata.get("web"),
        "color": metadata.get("color"),
        "register": metadata.get("register"),
        "components": metadata.get("components"),
        "baseline": bool(metadata.get("baseline")),
        "returncode": result.returncode,
        "cached": result.cached,
        "duration_seconds": result.duration_seconds,
        "cache_key": result.cache_key,
        "object": result.object_path,
        "comparison": compact_comparison,
        "failure": result.stderr[-2048:] if comparison is None else None,
    }


def _emitted_force_effect(
    baseline: CompileResult,
    forced: CompileResult,
    *,
    objdump: str | None,
    symbol: str | None,
    section: str,
) -> dict[str, Any]:
    """Describe what one force changed in emitted code.

    This is deliberately object-level attribution.  A changed field load often
    makes a web's role obvious to a human, but the report does not promote that
    observation into producer-emitted ``source_semantic`` evidence.
    """

    if baseline.object_path is None or forced.object_path is None:
        return {
            "schema": EFFECT_SCHEMA,
            "available": False,
            "reason": "baseline or forced object was not retained",
        }
    baseline_path = Path(baseline.object_path)
    forced_path = Path(forced.object_path)
    if not baseline_path.is_file() or not forced_path.is_file():
        return {
            "schema": EFFECT_SCHEMA,
            "available": False,
            "reason": "baseline or forced object is unavailable",
        }
    try:
        comparison = compare_objects(
            baseline_path,
            forced_path,
            objdump=objdump,
            symbol=symbol,
            section=section,
        )
    except (OSError, RuntimeError, ValueError) as error:
        return {
            "schema": EFFECT_SCHEMA,
            "available": False,
            "reason": str(error),
        }

    all_sites = comparison.diff_sites
    sites = [
        {
            "index": row.get("index"),
            "class": row.get("class"),
            "baseline": row.get("target"),
            "forced": row.get("candidate"),
        }
        for row in all_sites
        if row.get("class") != "relocation-controlled"
    ]
    relocation_sites = sum(
        row.get("class") == "relocation-controlled" for row in all_sites
    )
    register_only = bool(sites) and all(row["class"] == "register" for row in sites)
    if not sites and not relocation_sites and comparison.raw_word_mismatches == 0:
        classification = "no-emitted-effect"
    elif not sites and relocation_sites:
        classification = "relocation-only-effect"
    elif (
        register_only
        and comparison.instruction_delta == 0
        and comparison.opcode_mismatches == 0
    ):
        classification = "instruction-neutral-register-effect"
    else:
        classification = "emitted-code-effect"
    return {
        "schema": EFFECT_SCHEMA,
        "available": True,
        "classification": classification,
        "changed_site_count": len(sites),
        "relocation_controlled_site_count": relocation_sites,
        "changed_sites": sites,
        "raw_word_mismatches": comparison.raw_word_mismatches,
        "relocation_target_mismatches": comparison.relocation_target_mismatches,
        "instruction_delta": comparison.instruction_delta,
        "opcode_mismatches": comparison.opcode_mismatches,
        "aligned_total": comparison.aligned_total,
        "proof_boundary": (
            "Controlled baseline-to-force object delta. Instruction text can "
            "identify a likely value role, but this is not source_semantic and "
            "forced output is never an acceptable source match."
        ),
    }


def run_oracle_campaign(
    plan: Mapping[str, Any],
    *,
    source: str | Path,
    target: str | Path,
    template: str,
    environment: dict[str, str],
    cache_dir: str | Path,
    ledger: str | Path | None = None,
    jobs: int = 1,
    objdump: str | None = None,
    symbol: str | None = None,
    section: str = ".text",
    compile_cwd: str | Path | None = None,
    keep_objects: str | Path | None = None,
    timeout: float | None = 120.0,
    stream_limit: int = DEFAULT_STREAM_LIMIT,
    artifact_dir: str | Path | None = None,
) -> dict[str, Any]:
    """Compile the baseline and one source under every validated force cell."""

    if plan.get("schema") != PLAN_SCHEMA:
        raise ValueError(f"oracle sweep requires a {PLAN_SCHEMA} plan")
    procedure = int(plan["procedure"])
    if "CDX_FORCE" in environment:
        raise ValueError(
            "oracle owns CDX_FORCE; remove it from --env and select forces in the plan"
        )
    if "CDX_PROC" in environment and environment["CDX_PROC"] != str(procedure):
        raise ValueError(
            f"trace selected proc {procedure}, but --env supplied "
            f"CDX_PROC={environment['CDX_PROC']!r}"
        )
    base_environment = {**environment, "CDX_PROC": str(procedure)}
    variants = [
        ParameterizedCandidate(
            source=source,
            environment=base_environment,
            metadata={
                "schema": SWEEP_SCHEMA,
                "baseline": True,
                "force": None,
            },
        )
    ]
    for row in plan["forces"]:
        if not isinstance(row, dict) or not isinstance(row.get("force"), str):
            raise ValueError("oracle plan contains an invalid force row")
        variants.append(
            ParameterizedCandidate(
                source=source,
                environment={
                    **base_environment,
                    "CDX_FORCE": row["force"],
                },
                metadata={
                    "schema": SWEEP_SCHEMA,
                    "baseline": False,
                    **row,
                },
            )
        )
    results = run_parameterized_campaign(
        variants,
        target=target,
        template=template,
        cache_dir=cache_dir,
        ledger=ledger,
        jobs=jobs,
        objdump=objdump,
        symbol=symbol,
        section=section,
        compile_cwd=compile_cwd,
        keep_objects=keep_objects,
        stop_on_exact=False,
        timeout=timeout,
        stream_limit=stream_limit,
        artifact_dir=artifact_dir,
    )
    baseline_result = next(
        (
            result
            for result in results
            if isinstance(result.experiment, dict) and result.experiment.get("baseline")
        ),
        None,
    )
    compact = []
    for result in results:
        row = _compact_result(result)
        if not row["baseline"] and baseline_result is not None:
            row["emitted_effect"] = _emitted_force_effect(
                baseline_result,
                result,
                objdump=objdump,
                symbol=symbol,
                section=section,
            )
        compact.append(row)
    baseline = next((row for row in compact if row["baseline"]), None)
    forced = [row for row in compact if not row["baseline"]]
    forced.sort(
        key=lambda row: (
            row["comparison"] is None,
            (
                int(row["comparison"]["aligned_total"]),
                int(row["comparison"]["words"]),
            )
            if isinstance(row["comparison"], dict)
            else (),
            str(row["force"]),
        )
    )
    observed_exact_forces = [
        str(row["force"])
        for row in forced
        if isinstance(row["comparison"], dict) and row["comparison"]["exact"]
    ]
    baseline_comparison = (
        baseline.get("comparison") if isinstance(baseline, dict) else None
    )
    control_valid = isinstance(baseline_comparison, dict)
    baseline_exact = bool(
        isinstance(baseline_comparison, dict) and baseline_comparison.get("exact")
    )
    exact_rows = (
        [
            row
            for row in forced
            if isinstance(row["comparison"], dict) and row["comparison"]["exact"]
        ]
        if control_valid and not baseline_exact
        else []
    )
    exact_forces = [str(row["force"]) for row in exact_rows]
    force_widths = [
        len(row["components"])
        if isinstance(row.get("components"), list) and row["components"]
        else 1
        for row in exact_rows
    ]
    minimum_forces = min(force_widths, default=None)
    if not exact_forces:
        signature = None
    elif minimum_forces == 1:
        signature = (
            f"one-force-exact({exact_forces[0]})"
            if len(exact_forces) == 1
            else f"one-force-exact({len(exact_forces)} alternatives)"
        )
    else:
        minimum_rows = [
            force
            for force, width in zip(exact_forces, force_widths, strict=True)
            if width == minimum_forces
        ]
        signature = (
            f"force-set-exact({minimum_rows[0]})"
            if len(minimum_rows) == 1
            else f"force-set-exact({minimum_forces} controls; "
            f"{len(minimum_rows)} alternatives)"
        )
    return {
        "schema": SWEEP_SCHEMA,
        "evidence": "diagnostic-oracle",
        "procedure": procedure,
        "coverage": plan["coverage"],
        "planned_forces": len(plan["forces"]),
        "completed_forces": len(forced),
        "baseline": baseline,
        "results": forced,
        "control_valid": control_valid,
        "baseline_exact": baseline_exact,
        "observed_exact_forces": observed_exact_forces,
        "exact_forces": exact_forces,
        "minimum_forces_to_exact": minimum_forces,
        "signature": signature,
        "ledger": str(Path(ledger).expanduser().resolve()) if ledger else None,
        "objects": (
            str(Path(keep_objects).expanduser().resolve()) if keep_objects else None
        ),
        "proof": (
            "A forced exact row is causal only with a valid, non-exact unforced "
            "control. Forced compiler output is never an acceptable source match; "
            "return to source-level lifetime and priority levers."
        ),
        "warnings": (
            ["unforced baseline failed; exact force rows are not causal evidence"]
            if not control_valid
            else ["unforced baseline is already exact; no force closed a residual"]
            if baseline_exact
            else []
        ),
    }
