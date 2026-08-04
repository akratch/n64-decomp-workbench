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

FINGERPRINT_SCHEMA = "decomp-workbench-allocator-webs-v1"
DIFF_SCHEMA = "decomp-workbench-allocator-web-diff-v1"
STACK_SCHEMA = "decomp-workbench-stack-homes-v1"

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
SOURCE_FIELDS = ("file", "line", "source", "expr", "listing")
SOURCE_SEMANTIC_FIELD = "source_semantic"
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
    neighbors: tuple[int, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "fingerprint": self.fingerprint,
            "confidence": self.confidence,
            "phase": self.decision.phase_tag,
            "proc": self.decision.proc,
            "numeric_web": self.decision.web,
            "force_key": self.decision.force_key,
            "provenance": self.provenance,
            "source": self.source,
            "source_attribution": self.source_attribution,
            "neighbors": list(self.neighbors),
            "assigned_color": self.decision.assigned_color,
            "assigned_register": self.decision.assigned_register,
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
        packed = item.fields.get("neighbors", "")
        for value in packed.split(","):
            neighbor = optional_integer(value)
            if neighbor is not None:
                result[(proc, phase, web)].add(neighbor)
    return result


def semantic_webs(
    trace: GlobalColorTrace,
    *,
    proc: int | None = None,
) -> list[SemanticWeb]:
    """Derive stable handles from the trace's semantic provenance."""

    neighbors = _neighbor_map(trace)
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
        identity = {
            "phase": decision.phase_tag,
            "provenance": provenance,
        }
        fingerprint = hashlib.sha256(
            json.dumps(identity, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()[:20]
        evidence = len(provenance)
        confidence = "high" if evidence >= 6 else "medium" if evidence >= 3 else "low"
        result.append(
            SemanticWeb(
                fingerprint=fingerprint,
                confidence=confidence,
                decision=decision,
                provenance=provenance,
                source=source,
                source_attribution=attribution,
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
    return {
        "schema": FINGERPRINT_SCHEMA,
        "proof": (
            "Fingerprints align semantic provenance. Numeric web IDs are shown "
            "only as trace-local handles and are never treated as stable."
        ),
        "webs": [web.as_dict() for web in webs],
        "web_count": len(webs),
        "low_confidence": sum(web.confidence == "low" for web in webs),
        "source_attributed_webs": attributed,
        "run_local_unattributed_webs": len(webs) - attributed,
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
    rows = []
    for fingerprint in sorted(set(target_index) | set(candidate_index)):
        expected = target_index.get(fingerprint)
        actual = candidate_index.get(fingerprint)
        changed = []
        if expected is None or actual is None:
            changed.append("presence")
        else:
            if expected.decision.assigned_color != actual.decision.assigned_color:
                changed.append("assigned_color")
            if expected.decision.forbidden_colors != actual.decision.forbidden_colors:
                changed.append("forbidden_colors")
            if expected.source != actual.source:
                changed.append("source_correlation")
        if changed:
            rows.append(
                {
                    "fingerprint": fingerprint,
                    "changed": changed,
                    "target": expected.as_dict() if expected else None,
                    "candidate": actual.as_dict() if actual else None,
                    "target_forbidden_causes": (
                        _forbidden_causes(expected, target_webs) if expected else []
                    ),
                    "candidate_forbidden_causes": (
                        _forbidden_causes(actual, candidate_webs) if actual else []
                    ),
                }
            )
    return {
        "schema": DIFF_SCHEMA,
        "proof": (
            "Semantic alignment, not numeric web-line diff. Ambiguous "
            "fingerprints are withheld rather than guessed."
        ),
        "differences": rows,
        "difference_count": len(rows),
        "ambiguous_fingerprints": ambiguous,
        "target_webs": len(target_webs),
        "candidate_webs": len(candidate_webs),
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

    homes = [
        home
        for web in semantic_webs(trace, proc=proc)
        if (home := classify_stack_home(web)) is not None
    ]
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
    return {
        "schema": STACK_SCHEMA,
        "proof": (
            "Trace-derived virtual-home provenance. final_offset is null unless "
            "the producer explicitly recorded final frame layout."
        ),
        "homes": selected,
        "home_count": len(homes),
        "selected_count": len(selected),
        "kinds": dict(sorted(counts.items())),
        "offset": offset,
    }
