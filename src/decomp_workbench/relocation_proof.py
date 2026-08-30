"""Compose fallback-static and promoted-linked relocation evidence.

Object-level relocation metadata and final linked bytes answer different
questions. This receipt keeps both surfaces, binds every input by content hash,
and promotes only when ownership, site identities, and the linked byte range
all agree. It never upgrades fallback evidence into linked evidence.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from .evidence import (
    EvidenceError,
    artifact_record,
    load_json_object,
    verify_artifact_record,
)
from .linked_compare import LINKED_COMPARE_SCHEMA
from .reloc_surface import SURFACE_SCHEMA
from .relocation_identity import IDENTITY_REPORT_SCHEMA

PROOF_SCHEMA = "decomp-workbench-relocation-proof-v1"
EVIDENCE_SCHEMA = "decomp-workbench-hash-bound-artifacts-v1"


def _mapping(value: object, *, where: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise EvidenceError(f"{where} must be a JSON object")
    return value


def _integer(value: object, *, where: str) -> int:
    if isinstance(value, bool):
        raise EvidenceError(f"{where} must be an integer, not a boolean")
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        try:
            return int(value, 0)
        except ValueError:
            pass
    raise EvidenceError(f"{where} must be an integer")


def _report_evidence(report: Mapping[str, Any], *, where: str) -> Mapping[str, Any]:
    evidence = _mapping(report.get("evidence"), where=f"{where}.evidence")
    if evidence.get("schema") != EVIDENCE_SCHEMA:
        raise EvidenceError(
            f"{where}.evidence schema must be {EVIDENCE_SCHEMA}; regenerate the report"
        )
    return evidence


def _verify_evidence_artifacts(
    evidence: Mapping[str, Any], *, where: str
) -> list[dict[str, Any]]:
    artifacts = evidence.get("artifacts")
    if not isinstance(artifacts, Sequence) or isinstance(artifacts, str | bytes):
        raise EvidenceError(f"{where}.artifacts must be a list")
    if not artifacts:
        raise EvidenceError(f"{where}.artifacts must not be empty")
    return [
        verify_artifact_record(item, where=f"{where}.artifacts[{index}]")
        for index, item in enumerate(artifacts)
    ]


def _artifact_by_role(
    artifacts: Sequence[Mapping[str, Any]], role: str, *, where: str
) -> Mapping[str, Any]:
    selected = [item for item in artifacts if item.get("role") == role]
    if len(selected) != 1:
        raise EvidenceError(
            f"{where} requires exactly one artifact with role={role!r}; "
            f"found {len(selected)}"
        )
    return selected[0]


def _candidate_artifact(
    artifacts: Sequence[Mapping[str, Any]], candidate: Mapping[str, Any]
) -> Mapping[str, Any]:
    expected_path = Path(str(candidate["path"])).resolve()
    matches = [
        item
        for item in artifacts
        if item.get("role") == "candidate-object"
        and Path(str(item.get("path", ""))).resolve() == expected_path
    ]
    if len(matches) != 1:
        raise EvidenceError(
            "fallback-static report does not bind exactly one copy of the "
            "selected candidate object"
        )
    if matches[0].get("sha256") != candidate.get("sha256"):
        raise EvidenceError(
            "fallback-static report and selected candidate object disagree on SHA-256"
        )
    return matches[0]


def _selected_range(linked: Mapping[str, Any], symbol: str) -> Mapping[str, Any]:
    raw_ranges = linked.get("ranges")
    if not isinstance(raw_ranges, Sequence) or isinstance(raw_ranges, str | bytes):
        raise EvidenceError("promoted-linked report ranges must be a list")
    matches = [
        item
        for item in raw_ranges
        if isinstance(item, Mapping) and item.get("name") == symbol
    ]
    if len(matches) != 1:
        raise EvidenceError(
            f"promoted-linked report must contain exactly one range named {symbol!r}"
        )
    selected = matches[0]
    if selected.get("class") not in {"exact", "text-exact"}:
        raise EvidenceError(
            f"promoted-linked range {symbol!r} is {selected.get('class')!r}, not exact"
        )
    return selected


def _owner(
    fallback_evidence: Mapping[str, Any], selected_range: Mapping[str, Any]
) -> dict[str, Any]:
    module = _mapping(fallback_evidence.get("module"), where="fallback module")
    image_start = _integer(module.get("image_start"), where="module.image_start")
    start = _integer(selected_range.get("start"), where="linked range start")
    end = _integer(selected_range.get("end"), where="linked range end")
    if end <= start or start < image_start:
        raise EvidenceError("linked range does not lie inside the fallback module")
    module_offset = start - image_start
    size = end - start
    sections = module.get("sections")
    if not isinstance(sections, Sequence) or isinstance(sections, str | bytes):
        raise EvidenceError("fallback module sections must be a list")
    owners = []
    for raw in sections:
        if not isinstance(raw, Mapping):
            continue
        offset = _integer(raw.get("offset"), where="module section offset")
        extent = _integer(raw.get("size"), where="module section size")
        if offset <= module_offset and module_offset + size <= offset + extent:
            owners.append(raw)
    if len(owners) != 1:
        raise EvidenceError(
            "linked range must have exactly one owning module section; "
            f"found {len(owners)}"
        )
    return {
        "namespace": "module-section-offset",
        "module": module.get("name"),
        "section": owners[0].get("name"),
        "offset": module_offset,
        "size": size,
        "image_start": start,
        "image_end": end,
    }


def build_relocation_proof(
    *,
    fallback_report: str | Path,
    linked_report: str | Path,
    symbol: str,
    source: str | Path,
    candidate_object: str | Path,
) -> dict[str, Any]:
    """Build one deterministic proof receipt from two independently named surfaces."""

    if not symbol.strip():
        raise EvidenceError("symbol must be non-empty")
    fallback_path = Path(fallback_report).expanduser().resolve()
    linked_path = Path(linked_report).expanduser().resolve()
    fallback = load_json_object(fallback_path, where="fallback-static report")
    linked = load_json_object(linked_path, where="promoted-linked report")
    if fallback.get("schema") != SURFACE_SCHEMA:
        raise EvidenceError(f"fallback report schema must be {SURFACE_SCHEMA}")
    if linked.get("schema") != LINKED_COMPARE_SCHEMA:
        raise EvidenceError(f"linked report schema must be {LINKED_COMPARE_SCHEMA}")
    if fallback.get("ok") is not True:
        raise EvidenceError("fallback-static relocation surface contains conflicts")
    if fallback.get("corroborated") is not True:
        raise EvidenceError(
            "fallback-static surface lacks a shipped relocation-table corroboration"
        )
    identities = _mapping(fallback.get("identities"), where="fallback identities")
    if identities.get("schema") != IDENTITY_REPORT_SCHEMA:
        raise EvidenceError(
            "fallback-static report lacks a versioned project identity-provider result"
        )
    if identities.get("complete") is not True:
        raise EvidenceError(
            "fallback-static identities are incomplete or contradicted; "
            f"resolved={identities.get('resolved')} "
            f"unknown={identities.get('unknown')} "
            f"contradicted={identities.get('contradicted')}"
        )

    fallback_evidence = _report_evidence(fallback, where="fallback-static report")
    linked_evidence = _report_evidence(linked, where="promoted-linked report")
    fallback_artifacts = _verify_evidence_artifacts(
        fallback_evidence, where="fallback-static evidence"
    )
    linked_artifacts = _verify_evidence_artifacts(
        linked_evidence, where="promoted-linked evidence"
    )
    source_record = artifact_record(source, role="candidate-source")
    candidate_record = artifact_record(candidate_object, role="candidate-object")
    _candidate_artifact(fallback_artifacts, candidate_record)

    fallback_target = _artifact_by_role(
        fallback_artifacts, "target-image", where="fallback-static evidence"
    )
    linked_target = _artifact_by_role(
        linked_artifacts, "target-image", where="promoted-linked evidence"
    )
    if fallback_target.get("sha256") != linked_target.get("sha256"):
        raise EvidenceError(
            "fallback-static and promoted-linked surfaces use different target images"
        )
    _artifact_by_role(linked_artifacts, "built-image", where="promoted-linked evidence")
    selected = _selected_range(linked, symbol)
    owner = _owner(fallback_evidence, selected)
    return {
        "schema": PROOF_SCHEMA,
        "status": "PASS",
        "symbol": symbol,
        "owner": owner,
        "source_binding": {
            "status": "host-declared",
            "source": source_record,
            "candidate_object": candidate_record,
            "claim": (
                "The host declares that this source produced this candidate object; "
                "the workbench binds both contents but does not run or infer the build."
            ),
        },
        "surfaces": {
            "fallback_static": {
                "report": artifact_record(fallback_path, role="fallback-static-report"),
                "target_sha256": fallback_target["sha256"],
                "relocation_sites": identities.get("sites"),
                "exact_identities": identities.get("resolved"),
                "status": "complete",
                "claim": (
                    "Offset/type/identity evidence only; this surface does not claim "
                    "that final linked bytes are exact."
                ),
            },
            "promoted_linked": {
                "report": artifact_record(linked_path, role="promoted-linked-report"),
                "target_sha256": linked_target["sha256"],
                "range": dict(selected),
                "status": "exact",
                "claim": "The selected final linked image range is byte-exact.",
            },
        },
        "claim": (
            "PASS binds a corroborated fallback relocation surface and complete "
            "project-supplied site identities to an exact final linked byte range."
        ),
    }


def verify_relocation_proof(path: str | Path) -> dict[str, Any]:
    """Rebuild a receipt from its recorded inputs and compare it structurally."""

    receipt = load_json_object(path, where="relocation proof")
    if receipt.get("schema") != PROOF_SCHEMA:
        raise EvidenceError(f"relocation proof schema must be {PROOF_SCHEMA}")
    surfaces = _mapping(receipt.get("surfaces"), where="relocation proof surfaces")
    fallback = _mapping(surfaces.get("fallback_static"), where="fallback surface")
    linked = _mapping(surfaces.get("promoted_linked"), where="linked surface")
    binding = _mapping(receipt.get("source_binding"), where="source binding")
    source = _mapping(binding.get("source"), where="source binding source")
    candidate = _mapping(
        binding.get("candidate_object"), where="source binding candidate_object"
    )
    for where, record in (
        ("fallback report", fallback.get("report")),
        ("linked report", linked.get("report")),
        ("candidate source", source),
        ("candidate object", candidate),
    ):
        verify_artifact_record(record, where=where)
    rebuilt = build_relocation_proof(
        fallback_report=str(
            _mapping(fallback["report"], where="fallback report")["path"]
        ),
        linked_report=str(_mapping(linked["report"], where="linked report")["path"]),
        symbol=str(receipt.get("symbol", "")),
        source=str(source["path"]),
        candidate_object=str(candidate["path"]),
    )
    return {
        "schema": PROOF_SCHEMA,
        "verification": "AGREES" if rebuilt == receipt else "DISAGREES",
        "pass": rebuilt == receipt,
        "receipt": receipt,
        "rebuilt": rebuilt,
    }


__all__ = [
    "EVIDENCE_SCHEMA",
    "PROOF_SCHEMA",
    "build_relocation_proof",
    "verify_relocation_proof",
]
