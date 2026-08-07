"""Semantic allocator-web fingerprints, interference joins, and stack homes."""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from dataclasses import dataclass
from typing import Any

from .globalcolor import (
    AllocatorWebDecision,
    GlobalColorTrace,
    optional_integer,
    register_for_color,
)

FINGERPRINT_SCHEMA = "decomp-workbench-allocator-webs-v2"
DIFF_SCHEMA = "decomp-workbench-allocator-web-diff-v2"
STACK_SCHEMA = "decomp-workbench-stack-homes-v1"
ORIGIN_PROBE_SCHEMA = "decomp-workbench-origin-probe-v1"

PROVENANCE_FIELDS = (
    "dtype",
    "type",
    "raw10",
    "raw14",
    "table",
    "chain",
    "exprtable",
    "exprchain",
    "bb",
    "defbb",
    "usebbs",
    "ancestry",
    "owner_sym",
    "owner_type",
    "owner_dtype",
    "primary_ichain_table",
    "primary_ichain_chain",
    "expr_table",
    "expr_chain",
    "ir_bb",
    "source_span",
    "merge_lineage",
    "merge_lineage_scope",
    "semantic_reason",
)
# ``raw14`` is retained as trace evidence, but calibrated IDO captures show it
# changing when the same formation web is recreated in another compiler run.
# Treating that address-like word as identity turns allocator deltas into two
# false presence changes.  Keep fingerprint inputs explicit so future opaque
# observations cannot accidentally become identity merely by being displayed.
FINGERPRINT_FIELDS = tuple(field for field in PROVENANCE_FIELDS if field != "raw14")
FINGERPRINT_FIELDS += ("source_semantic",)
FINGERPRINT_EXCLUDED_OBSERVATIONS = ("raw14",)
SOURCE_FIELDS = ("file", "line", "source", "expr", "listing")
SOURCE_SEMANTIC_FIELD = "source_semantic"

# Deliberately excludes numeric web IDs, colors, source symbols/spans, merge IDs,
# and table IDs.  These fields often renumber after a one-line source edit.  The
# remaining fields describe the web's compiler-visible shape, but do not prove
# source identity; collisions are therefore reported rather than guessed away.
TOPOLOGY_FIELDS = (
    "dtype",
    "type",
    "chain",
    "exprchain",
    "bb",
    "defbb",
    "usebbs",
    "ancestry",
    "owner_type",
    "owner_dtype",
    "primary_ichain_chain",
    "expr_chain",
    "ir_bb",
    "merge_lineage_scope",
)
FORMATION_FIELDS = (
    "dtype",
    "type",
    "table",
    "chain",
    "exprtable",
    "exprchain",
    "bb",
)
ECONOMIC_DECISION_FIELDS = (
    "class",
    "save",
    "nocs",
    "totalsave",
    "numintf",
    "decision",
)
_MISSING_SOURCE_SEMANTICS = {
    "",
    "-",
    "n/a",
    "na",
    "none",
    "null",
    "unknown",
    "unavailable",
    "unattributed",
    "unset",
    "missing",
    "not-available",
    "not_available",
    "not-applicable",
    "not_applicable",
    "no-metadata",
    "no_metadata",
    "no-source-metadata",
    "no_source_metadata",
}


@dataclass(frozen=True)
class SemanticWeb:
    """One allocator web identified by semantic provenance, not its bit number."""

    fingerprint: str
    confidence: str
    decision: AllocatorWebDecision
    provenance: dict[str, str]
    source: dict[str, str]
    source_attribution: dict[str, str]
    formation: dict[str, Any]
    neighbors: tuple[int, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "fingerprint": self.fingerprint,
            "confidence": self.confidence,
            "phase": self.decision.phase_tag,
            "proc": self.decision.proc,
            "numeric_web": self.decision.web,
            "force_key": self.decision.force_key,
            "decision_trace_ordinal": self.decision.decision_trace_ordinal,
            "economics": {
                key: self.decision.fields.get(key)
                for key in ("save", "nocs", "totalsave")
                if self.decision.fields.get(key) is not None
            },
            "provenance": self.provenance,
            "source": self.source,
            "source_attribution": self.source_attribution,
            "formation": self.formation,
            "neighbors": list(self.neighbors),
            "assigned_color": self.decision.assigned_color,
            "assigned_register": self.decision.assigned_register,
            "natural_color": self.decision.natural_color,
            "natural_register": register_for_color(self.decision.natural_color),
            "forbidden_colors": self.decision.forbidden_colors,
            "forbidden_registers": [
                {
                    "color": color,
                    "register": register_for_color(color),
                }
                for color in self.decision.forbidden_colors
            ],
        }


def source_attribution(detail: dict[str, str]) -> dict[str, str]:
    """Classify whether a trace names a source-level semantic handle.

    Web IDs, colors, owner-like fields, compiler lineage, and logical lines
    identify one compiler run or help correlate retained evidence. None names
    the source operation being changed. Only an explicit producer-recorded
    ``source_semantic`` field earns source-experiment guidance. Explicit
    unavailable/no-metadata sentinel values remain run-local.
    """

    semantic = detail.get(SOURCE_SEMANTIC_FIELD, "").strip()
    if semantic.casefold() not in _MISSING_SOURCE_SEMANTICS:
        return {
            "classification": "source-attributed",
            "source_semantic": semantic,
        }
    return {
        "classification": "run-local-unattributed",
        "next_gate": (
            "Record a direct source_semantic for this web; line, owner, and "
            "lineage fields are run-local evidence, not source attribution."
        ),
    }


def _neighbor_map(trace: GlobalColorTrace) -> dict[tuple[int, str, int], set[int]]:
    result: dict[tuple[int, str, int], set[int]] = defaultdict(set)
    decision_phases: dict[tuple[int, int], set[str]] = defaultdict(set)
    for item in trace.decisions:
        if item.phase not in {"p1dec", "p2dec"}:
            continue
        proc = optional_integer(item.fields.get("proc"))
        web = optional_integer(item.fields.get("web"))
        if proc is not None and web is not None:
            decision_phases[(proc, web)].add(item.fields.get("phase") or item.phase[:2])
    for item in trace.decisions:
        proc = optional_integer(item.fields.get("proc"))
        web = optional_integer(item.fields.get("web"))
        if proc is None or web is None:
            continue
        phase = item.fields.get("phase") or item.phase[:2]
        if phase not in {"p1", "p2"}:
            phases = decision_phases.get((proc, web), set())
            if len(phases) != 1:
                continue
            phase = next(iter(phases))
        for key in ("neighbor", "other"):
            neighbor = optional_integer(item.fields.get(key))
            if neighbor is not None:
                result[(proc, phase, web)].add(neighbor)
        if item.phase == "forbidproducer":
            producer = optional_integer(item.fields.get("producer_web"))
            if producer is not None:
                result[(proc, phase, web)].add(producer)
        packed = item.fields.get("neighbors", "")
        for value in packed.split(","):
            neighbor = optional_integer(value)
            if neighbor is not None:
                result[(proc, phase, web)].add(neighbor)
    return result


def _formation_map(
    trace: GlobalColorTrace,
) -> tuple[
    dict[tuple[int, int, int], dict[str, Any]],
    dict[tuple[int, int], dict[str, Any]],
]:
    """Join opt-in formation events to the ICHAIN identity used by webdetail.

    Formation events precede run-local allocator web numbers.  Keeping this
    evidence separate from semantic identity lets the UI expose the ordering
    question without pretending that table IDs or event numbers are stable
    across source variants.
    """

    grouped: dict[tuple[int, int, int], dict[str, Any]] = {}
    range_events_by_proc: dict[int, list[int]] = defaultdict(list)
    for item in trace.lineage_for():
        fields = item.fields
        proc = optional_integer(fields.get("proc"))
        table = optional_integer(fields.get("table"))
        chain = optional_integer(fields.get("chain"))
        event = optional_integer(fields.get("event"))
        if None in {proc, table, chain}:
            continue
        assert proc is not None and table is not None and chain is not None
        key = (proc, table, chain)
        sym = optional_integer(fields.get("sym"))
        record = grouped.setdefault(
            key,
            {
                "status": "captured",
                "procedure_ordinal_basis": "makelivranges-invocation",
                "table": table,
                "chain": chain,
                "sym": sym,
                "range_event": None,
                "first_member_event": None,
                "first_member_bb": None,
                "member_bbs": [],
                "member_count": 0,
            },
        )
        if item.phase == "lineage_range":
            if event is not None:
                record["range_event"] = event
                range_events_by_proc[proc].append(event)
            continue
        bb = optional_integer(fields.get("bb"))
        record["member_count"] += 1
        if bb is not None and bb not in record["member_bbs"]:
            record["member_bbs"].append(bb)
        first_event = record["first_member_event"]
        if event is not None and (first_event is None or event < first_event):
            record["first_member_event"] = event
            record["first_member_bb"] = bb

    ranks = {
        proc: {event: rank for rank, event in enumerate(sorted(set(events)), 1)}
        for proc, events in range_events_by_proc.items()
    }
    for (proc, _table, _chain), record in grouped.items():
        event = record["range_event"]
        record["formation_rank"] = ranks.get(proc, {}).get(event)
        record["member_bbs"].sort()
    sym_groups: dict[tuple[int, int], list[dict[str, Any]]] = defaultdict(list)
    for (proc, _table, _chain), record in grouped.items():
        sym = record["sym"]
        if sym is not None:
            sym_groups[(proc, sym)].append(record)
    # A trace-local sym is only a safe fallback when it names exactly one
    # formation range in the procedure.  Ambiguous aliases are withheld.
    by_sym = {
        key: records[0] for key, records in sym_groups.items() if len(records) == 1
    }
    return grouped, by_sym


def semantic_webs(
    trace: GlobalColorTrace,
    *,
    proc: int | None = None,
) -> list[SemanticWeb]:
    """Derive stable handles from the trace's semantic provenance."""

    neighbors = _neighbor_map(trace)
    formations, formations_by_sym = _formation_map(trace)
    result = []
    for decision in trace.allocator_webs(proc=proc):
        provenance = {
            key: decision.detail[key]
            for key in PROVENANCE_FIELDS
            if decision.detail.get(key) not in {None, ""}
        }
        source = {
            key: decision.detail[key]
            for key in SOURCE_FIELDS
            if decision.detail.get(key) not in {None, ""}
        }
        attribution = source_attribution(decision.detail)
        table = optional_integer(decision.detail.get("table"))
        chain = optional_integer(decision.detail.get("chain"))
        sym = optional_integer(decision.fields.get("sym"))
        formation = (
            formations.get((decision.proc, table, chain))
            if table is not None and chain is not None
            else None
        )
        if formation is None and sym is not None:
            formation = formations_by_sym.get((decision.proc, sym))
        if formation is None:
            formation = {
                "status": "not-captured",
                "next_gate": (
                    "Capture this procedure with CDX_LINEAGE_TABLES=all (or "
                    "the web's ICHAIN table) to inspect formation order."
                ),
            }
        identity_provenance = {
            key: provenance[key] for key in FINGERPRINT_FIELDS if key in provenance
        }
        if attribution["classification"] == "source-attributed":
            identity_provenance[SOURCE_SEMANTIC_FIELD] = attribution[
                SOURCE_SEMANTIC_FIELD
            ]
        identity = {
            "phase": decision.phase_tag,
            "provenance": identity_provenance,
        }
        fingerprint = hashlib.sha256(
            json.dumps(identity, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()[:20]
        evidence = len(identity_provenance)
        confidence = "high" if evidence >= 6 else "medium" if evidence >= 3 else "low"
        result.append(
            SemanticWeb(
                fingerprint=fingerprint,
                confidence=confidence,
                decision=decision,
                provenance=provenance,
                source=source,
                source_attribution=attribution,
                formation=formation,
                neighbors=tuple(
                    sorted(neighbors[(decision.proc, decision.phase_tag, decision.web)])
                ),
            )
        )
    result.sort(
        key=lambda item: (
            item.decision.proc,
            item.decision.phase_tag,
            item.fingerprint,
            item.decision.web,
        )
    )
    return result


def web_report(trace: GlobalColorTrace, *, proc: int | None = None) -> dict[str, Any]:
    webs = semantic_webs(trace, proc=proc)
    attributed = sum(
        web.source_attribution["classification"] == "source-attributed" for web in webs
    )
    formation_captured = sum(web.formation["status"] == "captured" for web in webs)
    return {
        "schema": FINGERPRINT_SCHEMA,
        "proof": (
            "Fingerprints align semantic provenance. Numeric web IDs are shown "
            "only as trace-local handles and are never treated as stable. "
            "Opaque raw14 is retained as evidence but excluded from identity."
        ),
        "fingerprint_fields": list(FINGERPRINT_FIELDS),
        "fingerprint_excluded_observations": list(FINGERPRINT_EXCLUDED_OBSERVATIONS),
        "webs": [web.as_dict() for web in webs],
        "web_count": len(webs),
        "low_confidence": sum(web.confidence == "low" for web in webs),
        "source_attributed_webs": attributed,
        "run_local_unattributed_webs": len(webs) - attributed,
        "formation_captured_webs": formation_captured,
        "formation_order_guidance": (
            "Formation rank is construction chronology, not coloring priority. "
            "Economics reports save/nocs/totalsave at the decision, where "
            "nocs is the pass's compressed occurrence divisor and not an "
            "occurrence count. "
            "Decision-trace ordinal is the observed p1dec/p2dec order. Compare "
            "paired traces: these are separate observations, and no one scalar "
            "proves the source cause."
            if formation_captured
            else "Decision-trace ordinal shows observed selection order. Capture "
            "CDX_LINEAGE_TABLES separately to make construction chronology visible."
        ),
        "next_gate": (
            None
            if attributed
            else "Record a direct source_semantic before using this trace to "
            "recommend a source experiment."
        ),
    }


def _index_unique(
    webs: list[SemanticWeb],
) -> tuple[dict[str, SemanticWeb], set[str]]:
    grouped: dict[str, list[SemanticWeb]] = defaultdict(list)
    for web in webs:
        grouped[web.fingerprint].append(web)
    ambiguous = {key for key, items in grouped.items() if len(items) != 1}
    return (
        {key: items[0] for key, items in grouped.items() if len(items) == 1},
        ambiguous,
    )


def _forbidden_causes(
    web: SemanticWeb,
    all_webs: list[SemanticWeb],
) -> list[dict[str, Any]]:
    by_number = {
        item.decision.web: item
        for item in all_webs
        if item.decision.proc == web.decision.proc
        and item.decision.phase_tag == web.decision.phase_tag
    }
    causes = []
    for neighbor_number in web.neighbors:
        neighbor = by_number.get(neighbor_number)
        if neighbor is None or neighbor.decision.assigned_color is None:
            continue
        color = neighbor.decision.assigned_color
        if color not in web.decision.forbidden_colors:
            continue
        causes.append(
            {
                "color": color,
                "register": neighbor.decision.assigned_register,
                "neighbor_fingerprint": neighbor.fingerprint,
                "trace_local_neighbor": neighbor_number,
            }
        )
    return causes


def _causes_for_colors(
    causes: list[dict[str, Any]], colors: set[int]
) -> list[dict[str, Any]]:
    """Select blocker evidence for a directional forbidden-mask delta."""

    return [cause for cause in causes if cause["color"] in colors]


def _decision_outcome_schedule(webs: list[SemanticWeb]) -> list[dict[str, Any]]:
    """Return the allocator's observed endpoint sequence without claiming identity.

    Semantic fingerprints answer whether two decisions describe the same
    compiler-visible web.  This schedule answers a different question: whether
    two possibly different web topologies reached the same ordered register
    endpoints.  Keeping the views separate is essential for carrier
    substitution experiments, where source-distinct hidden webs can recreate
    an identical allocation cascade.
    """

    ordered = sorted(
        webs,
        key=lambda web: (
            web.decision.proc,
            web.decision.phase_tag,
            web.decision.decision_trace_ordinal,
            web.decision.web,
        ),
    )
    return [
        {
            "proc": web.decision.proc,
            "phase": web.decision.phase_tag,
            "ordinal": web.decision.decision_trace_ordinal,
            "decision": web.decision.fields.get("decision"),
            "assigned_color": web.decision.assigned_color,
            "assigned_register": web.decision.assigned_register,
            "natural_color": web.decision.natural_color,
            "natural_register": register_for_color(web.decision.natural_color),
        }
        for web in ordered
    ]


def _compare_decision_outcomes(
    target_webs: list[SemanticWeb], candidate_webs: list[SemanticWeb]
) -> dict[str, Any]:
    target = _decision_outcome_schedule(target_webs)
    candidate = _decision_outcome_schedule(candidate_webs)
    comparable = min(len(target), len(candidate))
    differences = []
    common_prefix = 0
    for index in range(comparable):
        before = target[index]
        after = candidate[index]
        changed = [
            field
            for field in (
                "proc",
                "phase",
                "ordinal",
                "decision",
                "assigned_color",
                "natural_color",
            )
            if before[field] != after[field]
        ]
        if not changed and common_prefix == index:
            common_prefix += 1
        if changed:
            differences.append(
                {
                    "index": index,
                    "changed": changed,
                    "target": before,
                    "candidate": after,
                }
            )
    for index in range(comparable, max(len(target), len(candidate))):
        differences.append(
            {
                "index": index,
                "changed": ["presence"],
                "target": target[index] if index < len(target) else None,
                "candidate": candidate[index] if index < len(candidate) else None,
            }
        )
    incomplete_rows = sum(
        item["assigned_color"] is None or item["natural_color"] is None
        for item in target + candidate
    )
    if not target and not candidate:
        status = "no-evidence"
    elif len(target) != len(candidate):
        status = "count-mismatch"
    elif differences:
        status = "different"
    elif incomplete_rows:
        status = "incomplete-evidence"
    else:
        status = "identical"
    target_phase_counts = {
        phase: sum(item["phase"] == phase for item in target)
        for phase in sorted({item["phase"] for item in target})
    }
    candidate_phase_counts = {
        phase: sum(item["phase"] == phase for item in candidate)
        for phase in sorted({item["phase"] for item in candidate})
    }
    return {
        "status": status,
        "identical": status == "identical",
        "target_count": len(target),
        "candidate_count": len(candidate),
        "common_prefix": common_prefix,
        "target_phase_counts": target_phase_counts,
        "candidate_phase_counts": candidate_phase_counts,
        "difference_count": len(differences),
        "incomplete_rows": incomplete_rows,
        "differences": differences,
        "target": target,
        "candidate": candidate,
        "proof": (
            "Observed decision-order/register endpoint equivalence only. "
            "It does not align semantic webs or prove equivalent source cause."
        ),
    }


def compare_semantic_webs(
    target: GlobalColorTrace,
    candidate: GlobalColorTrace,
    *,
    proc: int | None = None,
) -> dict[str, Any]:
    """Align two allocator traces by semantic provenance."""

    target_webs = semantic_webs(target, proc=proc)
    candidate_webs = semantic_webs(candidate, proc=proc)
    target_index, target_ambiguous = _index_unique(target_webs)
    candidate_index, candidate_ambiguous = _index_unique(candidate_webs)
    ambiguous = sorted(target_ambiguous | candidate_ambiguous)
    common_fingerprints = sorted(set(target_index) & set(candidate_index))
    comparable_denominator = len(set(target_index) | set(candidate_index))
    alignment_coverage = (
        len(common_fingerprints) / comparable_denominator
        if comparable_denominator
        else None
    )
    if not target_webs and not candidate_webs:
        alignment_status = "no-evidence"
        proof = (
            "Neither trace contains allocator-web evidence for the selected "
            "procedure. No alignment or equality claim is possible."
        )
        next_gate = (
            "Verify the procedure filter and capture globalcolor decision "
            "records before comparing allocator webs."
        )
    elif comparable_denominator and not common_fingerprints:
        alignment_status = "no-common-fingerprints"
        proof = (
            "No semantic alignment was established: every unique fingerprint "
            "changed presence. Treat this as fingerprint churn across a broad "
            "source-topology change, not as N proven web insertions/removals. "
            "Use trace-origin-probe on one controlled edit or capture producer "
            "source_semantic/formation lineage before interpreting decisions."
        )
        next_gate = (
            "Reduce the comparison to one controlled source edit with "
            "trace-origin-probe, or add producer-emitted source_semantic; this "
            "pair cannot support a web-by-web causal claim."
        )
    elif ambiguous or (alignment_coverage is not None and alignment_coverage < 1.0):
        alignment_status = "partial"
        proof = (
            "Semantic fingerprints align only the reported common subset; "
            "presence-only rows outside it may be provenance churn. Ambiguous "
            "fingerprints are withheld rather than guessed."
        )
        next_gate = (
            "Interpret decision deltas only for common fingerprints; calibrate "
            "presence changes with trace-origin-probe before source advice."
        )
    else:
        alignment_status = "aligned"
        proof = (
            "Semantic alignment, not numeric web-line diff. Ambiguous "
            "fingerprints are withheld rather than guessed. Opaque raw14 is "
            "retained as evidence but excluded from identity."
        )
        next_gate = None
    rows: list[dict[str, Any]] = []
    for fingerprint in sorted(set(target_index) | set(candidate_index)):
        expected = target_index.get(fingerprint)
        actual = candidate_index.get(fingerprint)
        changed = []
        if expected is None or actual is None:
            changed.append("presence")
        else:
            if expected.decision.assigned_color != actual.decision.assigned_color:
                changed.append("assigned_color")
            if expected.decision.natural_color != actual.decision.natural_color:
                changed.append("natural_color")
            if expected.decision.forbidden_colors != actual.decision.forbidden_colors:
                changed.append("forbidden_colors")
            if expected.source != actual.source:
                changed.append("source_correlation")
        if changed:
            target_causes = _forbidden_causes(expected, target_webs) if expected else []
            candidate_causes = (
                _forbidden_causes(actual, candidate_webs) if actual else []
            )
            target_colors = (
                set(expected.decision.forbidden_colors) if expected else set()
            )
            candidate_colors = (
                set(actual.decision.forbidden_colors) if actual else set()
            )
            rows.append(
                {
                    "fingerprint": fingerprint,
                    "changed": changed,
                    "target": expected.as_dict() if expected else None,
                    "candidate": actual.as_dict() if actual else None,
                    "target_forbidden_causes": target_causes,
                    "candidate_forbidden_causes": candidate_causes,
                    "target_only_forbidden_causes": _causes_for_colors(
                        target_causes, target_colors - candidate_colors
                    ),
                    "candidate_only_forbidden_causes": _causes_for_colors(
                        candidate_causes, candidate_colors - target_colors
                    ),
                }
            )
    return {
        "schema": DIFF_SCHEMA,
        "proof": proof,
        "next_gate": next_gate,
        "alignment_status": alignment_status,
        "common_fingerprints": len(common_fingerprints),
        "alignment_denominator": comparable_denominator,
        "alignment_coverage": alignment_coverage,
        "fingerprint_fields": list(FINGERPRINT_FIELDS),
        "fingerprint_excluded_observations": list(FINGERPRINT_EXCLUDED_OBSERVATIONS),
        "differences": rows,
        "difference_count": len(rows),
        "decision_summary": {
            "actual_assignment_changes": sum(
                "assigned_color" in row["changed"] for row in rows
            ),
            "natural_choice_changes": sum(
                "natural_color" in row["changed"] for row in rows
            ),
            "forbidden_mask_changes": sum(
                "forbidden_colors" in row["changed"] for row in rows
            ),
            "candidate_force_overrides": [
                {
                    "fingerprint": row["fingerprint"],
                    "force_key": row["candidate"]["force_key"],
                    "natural_register": row["candidate"]["natural_register"],
                    "assigned_register": row["candidate"]["assigned_register"],
                }
                for row in rows
                if row["candidate"] is not None
                and row["candidate"]["natural_color"]
                != row["candidate"]["assigned_color"]
            ],
        },
        "outcome_schedule": _compare_decision_outcomes(target_webs, candidate_webs),
        "ambiguous_fingerprints": ambiguous,
        "target_webs": len(target_webs),
        "candidate_webs": len(candidate_webs),
    }


def _topology_key(web: SemanticWeb) -> str:
    """Return a deliberately coarse, run-independent topology signature."""

    shape = {
        "phase": web.decision.phase_tag,
        "shape": {
            key: web.decision.detail[key]
            for key in TOPOLOGY_FIELDS
            if web.decision.detail.get(key) not in {None, ""}
        },
    }
    return hashlib.sha256(
        json.dumps(shape, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()[:20]


def _topology_groups(webs: list[SemanticWeb]) -> dict[str, list[SemanticWeb]]:
    grouped: dict[str, list[SemanticWeb]] = defaultdict(list)
    for web in webs:
        grouped[_topology_key(web)].append(web)
    return grouped


def _formation_key(web: SemanticWeb) -> str:
    """Return the detailed, run-local formation shape used for M0 probes."""

    shape = {
        "phase": web.decision.phase_tag,
        "formation": {
            key: web.decision.detail[key]
            for key in FORMATION_FIELDS
            if web.decision.detail.get(key) not in {None, ""}
        },
        "logical_line": web.source.get("line"),
    }
    return hashlib.sha256(
        json.dumps(shape, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()[:20]


def _formation_groups(webs: list[SemanticWeb]) -> dict[str, list[SemanticWeb]]:
    grouped: dict[str, list[SemanticWeb]] = defaultdict(list)
    for web in webs:
        grouped[_formation_key(web)].append(web)
    return grouped


def _economic_key(web: SemanticWeb) -> str:
    """Return a controlled-differential allocator-economics signature.

    Decision-phase and save/cost dimensions often survive wholesale ICHAIN
    renumbering and instrumentation-profile changes. They are not identities:
    several unrelated webs can have the same economics. The origin probe
    therefore exposes collisions and aligns only signatures unique on both
    sides.
    """

    shape = {
        "phase": web.decision.phase_tag,
        "decision": {
            key: web.decision.fields[key]
            for key in ECONOMIC_DECISION_FIELDS
            if web.decision.fields.get(key) not in {None, ""}
        },
    }
    return hashlib.sha256(
        json.dumps(shape, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()[:20]


def _economic_groups(webs: list[SemanticWeb]) -> dict[str, list[SemanticWeb]]:
    grouped: dict[str, list[SemanticWeb]] = defaultdict(list)
    for web in webs:
        grouped[_economic_key(web)].append(web)
    return grouped


def _economic_transitions(
    baseline_groups: dict[str, list[SemanticWeb]],
    variant_groups: dict[str, list[SemanticWeb]],
) -> list[dict[str, Any]]:
    """Describe changed unique economics signatures without claiming identity."""

    rows: list[dict[str, Any]] = []
    for key in sorted(set(baseline_groups) & set(variant_groups)):
        before = baseline_groups[key]
        after = variant_groups[key]
        if len(before) != 1 or len(after) != 1:
            continue
        baseline_web = before[0]
        variant_web = after[0]
        changed = []
        if baseline_web.decision.web != variant_web.decision.web:
            changed.append("trace_local_web")
        if baseline_web.decision.natural_color != variant_web.decision.natural_color:
            changed.append("natural_color")
        if baseline_web.decision.assigned_color != variant_web.decision.assigned_color:
            changed.append("assigned_color")
        if (
            baseline_web.decision.forbidden_colors
            != variant_web.decision.forbidden_colors
        ):
            changed.append("forbidden_colors")
        if changed:
            rows.append(
                {
                    "economics_fingerprint": key,
                    "changed": changed,
                    "baseline": {
                        "trace_local_web": baseline_web.decision.web,
                        "natural_color": baseline_web.decision.natural_color,
                        "natural_register": register_for_color(
                            baseline_web.decision.natural_color
                        ),
                        "assigned_color": baseline_web.decision.assigned_color,
                        "assigned_register": baseline_web.decision.assigned_register,
                    },
                    "variant": {
                        "trace_local_web": variant_web.decision.web,
                        "natural_color": variant_web.decision.natural_color,
                        "natural_register": register_for_color(
                            variant_web.decision.natural_color
                        ),
                        "assigned_color": variant_web.decision.assigned_color,
                        "assigned_register": variant_web.decision.assigned_register,
                    },
                }
            )
    return rows


def _multiset_delta(
    baseline_groups: dict[str, list[SemanticWeb]],
    variant_groups: dict[str, list[SemanticWeb]],
    *,
    fingerprint_label: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[str]]:
    removed: list[dict[str, Any]] = []
    added: list[dict[str, Any]] = []
    collision_keys: list[str] = []
    for key in sorted(set(baseline_groups) | set(variant_groups)):
        before = baseline_groups.get(key, [])
        after = variant_groups.get(key, [])
        if len(before) > 1 or len(after) > 1:
            collision_keys.append(key)
        delta = len(after) - len(before)
        row = {
            fingerprint_label: key,
            "baseline_count": len(before),
            "variant_count": len(after),
        }
        if delta < 0:
            removed.extend([row] * -delta)
        elif delta > 0:
            added.extend([row] * delta)
    return removed, added, collision_keys


def origin_probe_report(
    baseline: GlobalColorTrace,
    variant: GlobalColorTrace,
    *,
    role: str,
    proc: int | None = None,
    source_semantic: str | None = None,
    synthetic: bool = False,
) -> dict[str, Any]:
    """Classify one controlled source perturbation without inventing identity.

    Exact semantic fingerprints remain the primary evidence.  A second,
    deliberately coarse topology multiset answers the narrower calibration
    question: did the edit add/remove one compiler-visible web shape?  It is
    not source attribution, and collisions or color cascades make the result
    ambiguous by construction.
    """

    baseline_webs = semantic_webs(baseline, proc=proc)
    variant_webs = semantic_webs(variant, proc=proc)
    has_evidence = bool(baseline_webs or variant_webs)
    exact = compare_semantic_webs(baseline, variant, proc=proc)
    baseline_formation = _formation_groups(baseline_webs)
    variant_formation = _formation_groups(variant_webs)
    baseline_economics = _economic_groups(baseline_webs)
    variant_economics = _economic_groups(variant_webs)
    baseline_groups = _topology_groups(baseline_webs)
    variant_groups = _topology_groups(variant_webs)
    formation_removed, formation_added, formation_collisions = _multiset_delta(
        baseline_formation,
        variant_formation,
        fingerprint_label="formation_fingerprint",
    )
    topology_removed, topology_added, topology_collisions = _multiset_delta(
        baseline_groups,
        variant_groups,
        fingerprint_label="topology_fingerprint",
    )
    economics_removed, economics_added, economics_collisions = _multiset_delta(
        baseline_economics,
        variant_economics,
        fingerprint_label="economics_fingerprint",
    )
    economics_transitions = _economic_transitions(baseline_economics, variant_economics)
    allocation_economics_transitions = [
        row
        for row in economics_transitions
        if any(change != "trace_local_web" for change in row["changed"])
    ]
    economics_renumber_only = len(economics_transitions) - len(
        allocation_economics_transitions
    )

    presence_rows = [
        row for row in exact["differences"] if "presence" in row["changed"]
    ]
    common_change_rows = [
        row for row in exact["differences"] if "presence" not in row["changed"]
    ]
    color_cascade = sum(
        "assigned_color" in row["changed"] for row in common_change_rows
    )
    removed_count = len(formation_removed)
    added_count = len(formation_added)
    ambiguous = bool(formation_collisions or exact["ambiguous_fingerprints"])

    if not has_evidence:
        classification = "no-evidence"
    elif not exact["difference_count"]:
        classification = "no-effect"
    elif not removed_count and not added_count:
        classification = (
            "allocation-cascade-only" if color_cascade else "provenance-only"
        )
    elif ambiguous or color_cascade:
        classification = "ambiguous"
    elif removed_count == 1 and added_count == 0:
        classification = "isolated-removal"
    elif removed_count == 0 and added_count == 1:
        classification = "isolated-insertion"
    elif removed_count == 1 and added_count == 1:
        classification = "isolated-replacement"
    else:
        classification = "ambiguous"

    attributed = sum(
        web.source_attribution["classification"] == "source-attributed"
        for web in baseline_webs + variant_webs
    )
    cascade_warning = (
        "The controlled edit recolored existing webs without changing their "
        "formation multiset. Re-compare the compiled object: a forced color is "
        "diagnostic evidence, not a source solution, and collateral recolors "
        "can regress lanes that were already correct."
        if color_cascade
        else None
    )
    if not has_evidence:
        next_gate = (
            "Verify the procedure filter and capture globalcolor decision "
            "records in both runs before classifying the probe."
        )
    elif cascade_warning:
        next_gate = (
            "Re-compare the compiled object, then inspect every collateral "
            "recolor before translating the forced decision into source."
        )
    elif attributed == 0:
        next_gate = (
            "Treat this only as an M0 role anchor; record producer-emitted "
            "source_semantic or ICHAIN creation lineage before source advice."
        )
    else:
        next_gate = "Inspect the producer-attributed exact diff before source advice."

    return {
        "schema": ORIGIN_PROBE_SCHEMA,
        "role": role,
        "source_semantic_label": source_semantic,
        "evidence_status": "ready" if has_evidence else "no-allocator-web-evidence",
        "classification": classification,
        "claim_scope": (
            "synthetic-calibration" if synthetic else "controlled-differential"
        ),
        "proof": (
            "Exact fingerprints are primary. Run-local formation shapes may "
            "calibrate one controlled M0 edit but do not survive arbitrary "
            "compiler renumbering. Coarse topology exposes collisions and never "
            "proves that a web came from the named source role."
        ),
        "counts": {
            "baseline_webs": len(baseline_webs),
            "variant_webs": len(variant_webs),
            "exact_differences": exact["difference_count"],
            "exact_presence_differences": len(presence_rows),
            "common_web_color_changes": color_cascade,
            "formation_removed": removed_count,
            "formation_added": added_count,
            "formation_collisions": len(formation_collisions),
            "topology_removed": len(topology_removed),
            "topology_added": len(topology_added),
            "topology_collisions": len(topology_collisions),
            "economics_removed": len(economics_removed),
            "economics_added": len(economics_added),
            "economics_collisions": len(economics_collisions),
            "unique_economics_transitions": len(economics_transitions),
            "allocation_economics_transitions": len(allocation_economics_transitions),
            "economics_renumber_only": economics_renumber_only,
            "producer_source_attributed_webs": attributed,
        },
        "formation_removed": formation_removed,
        "formation_added": formation_added,
        "formation_collision_fingerprints": formation_collisions,
        "topology_removed": topology_removed,
        "topology_added": topology_added,
        "topology_collision_fingerprints": topology_collisions,
        "economics_removed": economics_removed,
        "economics_added": economics_added,
        "economics_collision_fingerprints": economics_collisions,
        "unique_economics_transitions": economics_transitions,
        "allocation_economics_transitions": allocation_economics_transitions,
        "cascade_warning": cascade_warning,
        "exact_diff": exact,
        "next_gate": next_gate,
    }


def _signed_32(value: int) -> int:
    return value - (1 << 32) if value & (1 << 31) else value


def classify_stack_home(web: SemanticWeb) -> dict[str, Any] | None:
    """Classify the virtual home only when the trace carries home evidence."""

    detail = web.decision.detail
    raw = optional_integer(detail.get("virtual_offset"))
    if raw is None and detail.get("raw14") == "0x04ae0102":
        raw = optional_integer(detail.get("raw10"))
    if raw is None:
        return None
    virtual_offset = _signed_32(raw & 0xFFFFFFFF)
    role = detail.get("role", "")
    symbol = detail.get("symbol") or detail.get("sym")
    if role in {"outgoing", "arg-home", "argument"}:
        kind = "outgoing-argument-home"
    elif symbol not in {None, "", "0", "-1"}:
        kind = "named-source-local"
    elif detail.get("spill") in {"1", "true", "yes"}:
        kind = "allocator-spill"
    else:
        kind = "compiler-temporary"
    final_offset = optional_integer(detail.get("final_offset"))
    return {
        "fingerprint": web.fingerprint,
        "confidence": web.confidence,
        "kind": kind,
        "virtual_offset": virtual_offset,
        "final_offset": final_offset,
        "source": web.source,
        "symbol": symbol,
        "phase": web.decision.phase_tag,
        "trace_local_web": web.decision.web,
    }


def stack_home_report(
    trace: GlobalColorTrace,
    *,
    proc: int | None = None,
    offset: int | None = None,
) -> dict[str, Any]:
    """Report stack-home ownership, optionally centered on a final offset."""

    webs = semantic_webs(trace, proc=proc)
    homes = [home for web in webs if (home := classify_stack_home(web)) is not None]
    selected = (
        [
            home
            for home in homes
            if home["final_offset"] == offset or home["virtual_offset"] == offset
        ]
        if offset is not None
        else homes
    )
    counts: dict[str, int] = defaultdict(int)
    for home in homes:
        counts[str(home["kind"])] += 1
    if not homes and webs:
        capture_status = "no-stack-home-evidence"
        next_gate = (
            f"The trace contains {len(webs)} allocator web(s), but none carry "
            "producer-emitted virtual_offset/final_offset evidence. The current "
            "globalcolor profile cannot answer this query; add a calibrated "
            "producer hook before recapturing. raw10/raw14 are opaque in this "
            "profile and are not inferred as frame offsets."
        )
    elif not homes:
        capture_status = "no-allocator-web-evidence"
        next_gate = (
            "No allocator webs were parsed for this procedure. Check --proc and "
            "capture a detailed globalcolor trace before querying stack homes."
        )
    elif offset is not None and not selected:
        capture_status = "offset-not-found"
        next_gate = (
            "Stack-home evidence exists, but no recorded virtual or final offset "
            f"equals {offset}."
        )
    else:
        capture_status = "ready"
        next_gate = None
    return {
        "schema": STACK_SCHEMA,
        "proof": (
            "Trace-derived virtual-home provenance. final_offset is null unless "
            "the producer explicitly recorded final frame layout."
        ),
        "homes": selected,
        "allocator_web_count": len(webs),
        "home_count": len(homes),
        "selected_count": len(selected),
        "kinds": dict(sorted(counts.items())),
        "offset": offset,
        "capture_status": capture_status,
        "next_gate": next_gate,
    }
