"""Immutable campaign current/best artifacts and guarded materialization."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .evidence import (
    artifact_record,
    exclusive_file_lock,
    file_sha256,
    verify_artifact_record,
    write_json_atomic,
)

ARTIFACT_SCHEMA = "decomp-workbench-candidate-artifact-v1"
POINTER_SCHEMA = "decomp-workbench-candidate-pointer-v1"
CHECKPOINT_SCHEMA = "decomp-workbench-campaign-checkpoint-v1"
RESTORE_SCHEMA = "decomp-workbench-campaign-restore-v1"
ACCEPT_SCHEMA = "decomp-workbench-campaign-accept-v1"


def _artifact_id(source_sha256: str, object_sha256: str | None) -> str:
    material = f"{source_sha256}\0{object_sha256 or '-'}".encode()
    return hashlib.sha256(material).hexdigest()[:24]


def _copy_exclusive(source: Path, destination: Path, expected: str) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        if not destination.is_file() or file_sha256(destination) != expected:
            raise ValueError(f"immutable campaign artifact changed: {destination}")
        return
    descriptor = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
    try:
        with os.fdopen(descriptor, "wb") as output, source.open("rb") as input_file:
            shutil.copyfileobj(input_file, output, length=1024 * 1024)
            output.flush()
            os.fsync(output.fileno())
    except BaseException:
        destination.unlink(missing_ok=True)
        raise
    if file_sha256(destination) != expected:
        destination.unlink(missing_ok=True)
        raise ValueError(f"campaign artifact copy failed verification: {destination}")


def archive_candidate(
    campaign_directory: str | Path,
    *,
    source: str | Path,
    object_path: str | Path | None,
) -> dict[str, Any]:
    """Archive one source/object pair by content identity; never overwrite it."""

    source_path = Path(source).expanduser().resolve()
    source_record = artifact_record(source_path, role="candidate-source")
    object_record = (
        artifact_record(object_path, role="candidate-object")
        if object_path is not None
        else None
    )
    identifier = _artifact_id(
        str(source_record["sha256"]),
        str(object_record["sha256"]) if object_record is not None else None,
    )
    directory = Path(campaign_directory) / "artifacts" / identifier
    with exclusive_file_lock(directory.parent / f".{identifier}.lock"):
        source_copy = directory / "source"
        _copy_exclusive(source_path, source_copy, str(source_record["sha256"]))
        object_copy = None
        if object_record is not None:
            object_source = Path(str(object_record["path"]))
            object_copy = directory / "object"
            _copy_exclusive(object_source, object_copy, str(object_record["sha256"]))
        record = {
            "schema": ARTIFACT_SCHEMA,
            "id": identifier,
            "source": artifact_record(source_copy, role="archived-source"),
            "object": (
                artifact_record(object_copy, role="archived-object")
                if object_copy is not None
                else None
            ),
        }
        metadata = directory / "artifact.json"
        if metadata.exists():
            existing = json.loads(metadata.read_text(encoding="utf-8"))
            if existing != record:
                raise ValueError(f"immutable candidate metadata disagrees: {metadata}")
        else:
            write_json_atomic(metadata, record)
        return record


def _candidate_pointer(
    artifact: Mapping[str, Any],
    *,
    role: str,
    source: str | Path,
    object_path: str | Path | None,
    comparison: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Attach mutable campaign context to one immutable content artifact."""

    return {
        "schema": POINTER_SCHEMA,
        "role": role,
        "id": artifact["id"],
        "artifact": dict(artifact),
        "origin": {
            "source": artifact_record(source, role="candidate-source"),
            "object": (
                artifact_record(object_path, role="candidate-object")
                if object_path is not None
                else None
            ),
        },
        "comparison": dict(comparison) if comparison is not None else None,
    }


def _pointer_artifact(pointer: Mapping[str, Any], *, role: str) -> Mapping[str, Any]:
    if pointer.get("schema") != POINTER_SCHEMA:
        raise ValueError(f"{role} checkpoint schema must be {POINTER_SCHEMA}")
    artifact = pointer.get("artifact")
    if not isinstance(artifact, Mapping) or artifact.get("schema") != ARTIFACT_SCHEMA:
        raise ValueError(f"{role} checkpoint has no immutable candidate artifact")
    if pointer.get("id") != artifact.get("id"):
        raise ValueError(f"{role} checkpoint and candidate artifact IDs disagree")
    return artifact


def _verify_archived_artifact(
    artifact: Mapping[str, Any], *, campaign_directory: Path, role: str
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    """Prove a candidate record names its content-addressed archive exactly."""

    identifier = artifact.get("id")
    if not isinstance(identifier, str) or len(identifier) != 24:
        raise ValueError(f"{role} candidate has an invalid artifact id")
    source = verify_artifact_record(
        artifact.get("source"), where=f"archived {role} source"
    )
    object_value = artifact.get("object")
    object_record = (
        verify_artifact_record(object_value, where=f"archived {role} object")
        if object_value is not None
        else None
    )
    expected_id = _artifact_id(
        str(source["sha256"]),
        str(object_record["sha256"]) if object_record is not None else None,
    )
    if identifier != expected_id:
        raise ValueError(f"{role} candidate id disagrees with archived contents")
    directory = (campaign_directory / "artifacts" / identifier).resolve()
    if Path(str(source["path"])) != directory / "source":
        raise ValueError(f"{role} candidate source is outside its immutable archive")
    if (
        object_record is not None
        and Path(str(object_record["path"])) != directory / "object"
    ):
        raise ValueError(f"{role} candidate object is outside its immutable archive")
    metadata = directory / "artifact.json"
    try:
        recorded = json.loads(metadata.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(
            f"cannot validate immutable candidate metadata: {error}"
        ) from None
    if recorded != dict(artifact):
        raise ValueError(f"{role} candidate disagrees with immutable metadata")
    return source, object_record


def _source_record_for_best(
    manifest: Mapping[str, Any], best: Mapping[str, Any]
) -> Mapping[str, Any]:
    cache_key = best.get("cache_key")
    matches = [
        item
        for item in manifest.get("sources", [])
        if isinstance(item, Mapping) and item.get("cache_key") == cache_key
    ]
    if len(matches) != 1:
        raise ValueError("best campaign candidate has no unique source record")
    return matches[0]


def _checkpoint_campaign_locked(
    manifest_path: str | Path,
    *,
    current_source: str | Path | None = None,
    current_object: str | Path | None = None,
) -> dict[str, Any]:
    """Archive the ranked best and, when named, the independently current state."""

    from .campaign_state import (
        build_status,
        durable_source_path,
        load_manifest,
        resolve_manifest,
    )

    path = resolve_manifest(manifest_path)
    manifest = load_manifest(path)
    status = build_status(path)
    best = status.get("best")
    if not isinstance(best, Mapping):
        raise ValueError("campaign has no successful candidate to checkpoint")
    source_record = _source_record_for_best(manifest, best)
    best_source = durable_source_path(source_record)
    if best.get("source_sha256") != source_record.get("sha256"):
        raise ValueError("best campaign source hash disagrees with its manifest record")
    cache_key = str(best.get("cache_key", ""))
    best_object = Path(str(manifest["cache_directory"])) / f"{cache_key}.o"
    if not best_object.is_file():
        raise FileNotFoundError(f"best candidate object is absent: {best_object}")
    if best.get("object_sha256") != file_sha256(best_object):
        raise ValueError("best campaign object hash disagrees with its ledger record")
    best_archive = archive_candidate(
        path.parent,
        source=best_source,
        object_path=best_object,
    )
    best_artifact = _candidate_pointer(
        best_archive,
        role="best",
        source=best_source,
        object_path=best_object,
        comparison=(
            best.get("comparison")
            if isinstance(best.get("comparison"), Mapping)
            else None
        ),
    )
    current_artifact = None
    if current_source is not None:
        current_archive = archive_candidate(
            path.parent,
            source=current_source,
            object_path=current_object,
        )
        current_artifact = _candidate_pointer(
            current_archive,
            role="current",
            source=current_source,
            object_path=current_object,
            comparison=None,
        )
    artifacts = dict(manifest.get("artifacts") or {})
    artifacts["best"] = best_artifact
    if current_artifact is not None:
        artifacts["current"] = current_artifact
    manifest["artifacts"] = artifacts
    write_json_atomic(path, manifest)
    return {
        "schema": CHECKPOINT_SCHEMA,
        "manifest": str(path),
        "current": current_artifact,
        "best": best_artifact,
        "same": (
            current_artifact is not None
            and current_artifact["id"] == best_artifact["id"]
        ),
    }


def _restore_best_locked(
    manifest_path: str | Path,
    *,
    destination: str | Path,
    allow_drift: bool = False,
) -> dict[str, Any]:
    """Materialize archived best source, backing up and drift-checking current data."""

    from .campaign_state import load_manifest, resolve_manifest

    path = resolve_manifest(manifest_path)
    manifest = load_manifest(path)
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, Mapping) or not isinstance(
        artifacts.get("best"), Mapping
    ):
        raise ValueError("campaign has no best checkpoint; run campaign checkpoint")
    best = artifacts["best"]
    archived = _pointer_artifact(best, role="best")
    source_record, _ = _verify_archived_artifact(
        archived, campaign_directory=path.parent, role="best"
    )
    archived_source = Path(str(source_record["path"]))
    expected_best = str(source_record["sha256"])
    target = Path(destination).expanduser().resolve()
    backup = None
    before = None
    if target.exists():
        before = artifact_record(target, role="destination-before")
        current = artifacts.get("current")
        if (
            not allow_drift
            and isinstance(current, Mapping)
            and isinstance(current.get("origin"), Mapping)
            and isinstance(current["origin"].get("source"), Mapping)
            and Path(str(current["origin"]["source"].get("path", ""))).resolve()
            == target
            and current["origin"]["source"].get("sha256") != before["sha256"]
        ):
            raise ValueError(
                "destination changed since the current checkpoint; checkpoint it "
                "again or pass --allow-drift explicitly"
            )
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        backup_dir = path.parent / "backups"
        backup_dir.mkdir(parents=True, exist_ok=True)
        backup = backup_dir / f"{stamp}-{str(before['sha256'])[:12]}{target.suffix}"
        _copy_exclusive(target, backup, str(before["sha256"]))
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(f".{target.name}.restore-{best['id']}")
    if temporary.exists():
        raise FileExistsError(f"stale restore temporary exists: {temporary}")
    _copy_exclusive(archived_source, temporary, expected_best)
    try:
        if before is None:
            if target.exists():
                raise ValueError(
                    "destination appeared during restore; refusing overwrite"
                )
        else:
            current = artifact_record(target, role="destination-before-install")
            if current["sha256"] != before["sha256"]:
                raise ValueError(
                    "destination changed during restore; refusing overwrite"
                )
        os.replace(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)
    after = artifact_record(target, role="destination-after")
    if after["sha256"] != expected_best:
        raise ValueError("restored source failed its final hash check")
    return {
        "schema": RESTORE_SCHEMA,
        "manifest": str(path),
        "best_id": best["id"],
        "destination": str(target),
        "before": before,
        "after": after,
        "backup": artifact_record(backup, role="backup") if backup else None,
    }


def _accept_best_locked(
    manifest_path: str | Path, *, allow_mismatch: bool = False
) -> dict[str, Any]:
    """Point the manifest at an immutable checkpoint.

    The checkpoint must be exact unless the caller explicitly waives that gate.
    """

    from .campaign_state import load_manifest, resolve_manifest

    path = resolve_manifest(manifest_path)
    manifest = load_manifest(path)
    artifacts = manifest.get("artifacts")
    best = artifacts.get("best") if isinstance(artifacts, Mapping) else None
    if not isinstance(best, Mapping):
        raise ValueError("campaign has no best checkpoint; run campaign checkpoint")
    artifact = _pointer_artifact(best, role="best")
    source, object_record = _verify_archived_artifact(
        artifact, campaign_directory=path.parent, role="best"
    )
    comparison = best.get("comparison")
    exact = isinstance(comparison, Mapping) and comparison.get("exact") is True
    if not exact and not allow_mismatch:
        raise ValueError(
            "best checkpoint is not exact; pass --allow-mismatch only for an "
            "intentional non-terminal acceptance"
        )
    accepted = {
        "artifact_id": best["id"],
        "source_sha256": source["sha256"],
        "object_sha256": object_record["sha256"] if object_record else None,
        "exact": exact,
    }
    manifest["accepted"] = accepted
    write_json_atomic(path, manifest)
    return {"schema": ACCEPT_SCHEMA, "manifest": str(path), "accepted": accepted}


def checkpoint_campaign(
    manifest_path: str | Path,
    *,
    current_source: str | Path | None = None,
    current_object: str | Path | None = None,
) -> dict[str, Any]:
    """Archive current/best under one manifest transaction lock."""

    from .campaign_state import manifest_lock_path, resolve_manifest

    path = resolve_manifest(manifest_path)
    with exclusive_file_lock(manifest_lock_path(path)):
        return _checkpoint_campaign_locked(
            path,
            current_source=current_source,
            current_object=current_object,
        )


def restore_best(
    manifest_path: str | Path,
    *,
    destination: str | Path,
    allow_drift: bool = False,
) -> dict[str, Any]:
    """Restore best under the same lock used by checkpoint and acceptance."""

    from .campaign_state import manifest_lock_path, resolve_manifest

    path = resolve_manifest(manifest_path)
    with exclusive_file_lock(manifest_lock_path(path)):
        return _restore_best_locked(
            path, destination=destination, allow_drift=allow_drift
        )


def accept_best(
    manifest_path: str | Path, *, allow_mismatch: bool = False
) -> dict[str, Any]:
    """Accept best under the same lock used by checkpoint and restoration."""

    from .campaign_state import manifest_lock_path, resolve_manifest

    path = resolve_manifest(manifest_path)
    with exclusive_file_lock(manifest_lock_path(path)):
        return _accept_best_locked(path, allow_mismatch=allow_mismatch)


__all__ = [
    "ACCEPT_SCHEMA",
    "ARTIFACT_SCHEMA",
    "CHECKPOINT_SCHEMA",
    "POINTER_SCHEMA",
    "RESTORE_SCHEMA",
    "accept_best",
    "archive_candidate",
    "checkpoint_campaign",
    "restore_best",
]
