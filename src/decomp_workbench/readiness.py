"""Freshness- and proof-aware classification for a matching target queue."""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from typing import Any

from .evidence import EvidenceError, load_json_object, verify_artifact_record
from .reloc_surface import SURFACE_SCHEMA
from .relocation_identity import IDENTITY_REPORT_SCHEMA
from .relocation_proof import EVIDENCE_SCHEMA

QUEUE_SCHEMA = "decomp-workbench-target-queue-v1"
READINESS_SCHEMA = "decomp-workbench-target-readiness-v1"
CLASSES = (
    "promotion-ready",
    "codegen-ready",
    "identity-maintenance",
    "remeasure",
)


def _entry_artifacts(value: Mapping[str, Any], *, where: str) -> list[object]:
    artifacts = value.get("artifacts")
    if not isinstance(artifacts, Sequence) or isinstance(artifacts, str | bytes):
        raise EvidenceError(f"{where}.artifacts must be a non-empty list")
    if not artifacts:
        raise EvidenceError(f"{where}.artifacts must be a non-empty list")
    return list(artifacts)


def _relocation_state(record: object) -> tuple[bool, str]:
    current_report = verify_artifact_record(record, where="relocation report")
    report = load_json_object(current_report["path"], where="relocation report")
    if report.get("schema") != SURFACE_SCHEMA:
        raise EvidenceError(f"relocation report schema must be {SURFACE_SCHEMA}")
    evidence = report.get("evidence")
    if not isinstance(evidence, Mapping) or evidence.get("schema") != EVIDENCE_SCHEMA:
        raise EvidenceError(
            "relocation report has no versioned hash-bound evidence; regenerate it"
        )
    artifacts = evidence.get("artifacts")
    if not isinstance(artifacts, Sequence) or isinstance(artifacts, str | bytes):
        raise EvidenceError("relocation report evidence artifacts must be a list")
    if not artifacts:
        raise EvidenceError("relocation report evidence artifacts must not be empty")
    for index, artifact in enumerate(artifacts):
        verify_artifact_record(
            artifact, where=f"relocation report evidence artifacts[{index}]"
        )
    identities = report.get("identities")
    if (
        not isinstance(identities, Mapping)
        or identities.get("schema") != IDENTITY_REPORT_SCHEMA
    ):
        return False, "relocation report has no project identity-provider result"
    if identities.get("complete") is True:
        return True, "every relocation site has one exact project identity"
    return (
        False,
        "relocation identities incomplete: "
        f"resolved={identities.get('resolved')} unknown={identities.get('unknown')} "
        f"contradicted={identities.get('contradicted')}",
    )


def classify_target(raw: object, *, index: int) -> dict[str, Any]:
    """Classify one target without allowing stale measurements into a work queue."""

    where = f"target queue entry {index}"
    if not isinstance(raw, Mapping):
        raise EvidenceError(f"{where} must be an object")
    symbol = raw.get("symbol")
    if not isinstance(symbol, str) or not symbol.strip():
        raise EvidenceError(f"{where}.symbol must be a non-empty string")
    stale_reasons: list[str] = []
    current_artifacts: list[dict[str, Any]] = []
    for artifact_index, artifact in enumerate(_entry_artifacts(raw, where=where)):
        try:
            current_artifacts.append(
                verify_artifact_record(
                    artifact, where=f"{where}.artifacts[{artifact_index}]"
                )
            )
        except EvidenceError as error:
            stale_reasons.append(str(error))
    measurement = raw.get("measurement")
    if not isinstance(measurement, Mapping):
        stale_reasons.append("no measured comparison is recorded")
        measurement = {}
    if stale_reasons:
        return {
            "symbol": symbol,
            "class": "remeasure",
            "reasons": stale_reasons,
            "next": "rebuild and regenerate the comparison before source or proof work",
            "artifacts": current_artifacts,
        }

    exact = measurement.get("exact") is True
    relocation_required = raw.get("relocation_required") is True
    relocation_record = raw.get("relocation_report")
    identities_complete = not relocation_required
    identity_reason = "target declares no project relocation identity requirement"
    if relocation_record is not None:
        try:
            identities_complete, identity_reason = _relocation_state(relocation_record)
        except (EvidenceError, OSError, ValueError) as error:
            return {
                "symbol": symbol,
                "class": "remeasure",
                "reasons": [f"relocation report cannot be trusted: {error}"],
                "next": "regenerate the relocation report from current artifacts",
                "artifacts": current_artifacts,
            }
    elif relocation_required:
        identity_reason = "target requires relocation identities but has no report"

    plateau = raw.get("plateau") is True
    if relocation_required and not identities_complete:
        klass = "identity-maintenance"
        next_step = (
            "complete canonical site identities before assigning source variants"
        )
    elif exact:
        klass = "promotion-ready"
        next_step = "run the final linked proof and project verification gates"
    else:
        klass = "codegen-ready"
        next_step = (
            "route only to a new evidence-producing mechanism; prior source "
            "space plateaued"
            if plateau
            else "assign source/codegen work using the recorded mismatch class"
        )
    return {
        "symbol": symbol,
        "class": klass,
        "reasons": [identity_reason],
        "next": next_step,
        "plateau": plateau,
        "measurement": dict(measurement),
        "artifacts": current_artifacts,
    }


def readiness_report(value: object) -> dict[str, Any]:
    """Classify every queue entry and keep maintenance out of source-work lanes."""

    if not isinstance(value, Mapping) or value.get("schema") != QUEUE_SCHEMA:
        raise EvidenceError(f"target queue schema must be {QUEUE_SCHEMA}")
    entries = value.get("entries")
    if not isinstance(entries, Sequence) or isinstance(entries, str | bytes):
        raise EvidenceError("target queue entries must be a list")
    rows = [classify_target(entry, index=index) for index, entry in enumerate(entries)]
    counts = Counter(str(row["class"]) for row in rows)
    return {
        "schema": READINESS_SCHEMA,
        "targets": rows,
        "counts": {klass: counts.get(klass, 0) for klass in CLASSES},
        "source_queue": [
            row["symbol"] for row in rows if row["class"] == "codegen-ready"
        ],
        "maintenance_queue": [
            row["symbol"]
            for row in rows
            if row["class"] in {"identity-maintenance", "remeasure"}
        ],
        "promotion_queue": [
            row["symbol"] for row in rows if row["class"] == "promotion-ready"
        ],
    }


__all__ = [
    "CLASSES",
    "QUEUE_SCHEMA",
    "READINESS_SCHEMA",
    "classify_target",
    "readiness_report",
]
