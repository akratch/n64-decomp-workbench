"""Durable campaign manifests, status, resume validation, and exports."""

from __future__ import annotations

import hashlib
import json
import os
import re
import time
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

from .campaign import (
    Candidate,
    executable_identity,
    file_sha256,
    render_compile_command,
)
from .model import display_path
from .toolchain import MANIFEST_NAME as TOOLCHAIN_MANIFEST_NAME
from .toolchain import toolchain_status

MANIFEST_SCHEMA = "decomp-workbench-campaign-manifest-v1"
STATUS_SCHEMA = "decomp-workbench-campaign-status-v1"
EXPORT_SCHEMA = "decomp-workbench-campaign-export-v1"
DEFAULT_STATE_ROOT = Path(".decomp-workbench")
EXPORT_TRAJECTORY_LIMIT = 2000
EXPORT_TRANSITION_LIMIT = 2000
EXPORT_FAILURE_LIMIT = 256
EXPORT_BASIN_SOURCE_LIMIT = 256


def _canonical_json(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _write_json_atomic(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def _slug(value: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9._-]+", "-", value).strip("-._")
    return normalized[:48] or "campaign"


def campaign_identity(
    *,
    target: Path,
    symbol: str | None,
    section: str,
    template: str,
    compile_cwd: Path,
    environment: Mapping[str, str],
    objdump: str,
    toolchain: str | Path | None = None,
) -> tuple[str, dict[str, Any]]:
    """Return a stable run identity and its human-auditable inputs."""

    command = render_compile_command(
        template,
        Path("__SOURCE__"),
        Path("__OUTPUT__"),
    )
    payload: dict[str, Any] = {
        "target": {
            "path": str(target),
            "sha256": file_sha256(target),
        },
        "symbol": symbol,
        "section": section,
        "compile": {
            "template": template,
            "working_directory": str(compile_cwd),
            "environment": dict(sorted(environment.items())),
            "compiler": executable_identity(command, cwd=compile_cwd),
        },
        "objdump": executable_identity([objdump], cwd=compile_cwd),
    }
    if toolchain is not None:
        report = toolchain_status(toolchain)
        manifest_path = Path(report["directory"]) / TOOLCHAIN_MANIFEST_NAME
        payload["toolchain"] = {
            "directory": report["directory"],
            "claim": report["claim"],
            "integrity": report["integrity"],
            "manifest": str(manifest_path),
            "manifest_sha256": file_sha256(manifest_path),
        }
    return hashlib.sha256(_canonical_json(payload)).hexdigest(), payload


def initialize_manifest(
    candidates: Iterable[Candidate],
    *,
    identity: str,
    identity_inputs: dict[str, Any],
    state_root: str | Path = DEFAULT_STATE_ROOT,
    ledger: str | Path | None = None,
    cache_dir: str | Path,
    artifact_dir: str | Path | None,
    jobs: int,
    timeout: float | None,
    stop_on_exact: bool,
    experiment: dict[str, Any] | None = None,
) -> tuple[Path, Path, dict[str, Any]]:
    """Create or extend the one manifest for a reproducible campaign identity."""

    target_name = Path(identity_inputs["target"]["path"]).stem
    label = identity_inputs.get("symbol") or target_name
    root = Path(state_root).expanduser().resolve()
    campaign_dir = root / "campaigns" / f"{_slug(str(label))}-{identity[:12]}"
    manifest_path = campaign_dir / "manifest.json"
    ledger_path = (
        Path(ledger).expanduser().resolve() if ledger else campaign_dir / "ledger.jsonl"
    )
    now = time.time()
    source_records = [
        {
            "path": str(candidate.source),
            "sha256": candidate.provenance["source_sha256"],
            "cache_key": candidate.cache_key,
        }
        for candidate in candidates
    ]
    if manifest_path.is_file():
        manifest = load_manifest(manifest_path)
        if manifest.get("identity") != identity:
            raise ValueError(
                f"campaign manifest identity changed unexpectedly: {manifest_path}"
            )
        existing = {
            str(item["cache_key"]): item
            for item in manifest.get("sources", [])
            if isinstance(item, dict) and "cache_key" in item
        }
        existing.update({str(item["cache_key"]): item for item in source_records})
        source_records = list(existing.values())
        created = manifest.get("created_at_unix", now)
    else:
        created = now
    manifest = {
        "schema": MANIFEST_SCHEMA,
        "identity": identity,
        "created_at_unix": created,
        "updated_at_unix": now,
        "status": "running",
        "identity_inputs": identity_inputs,
        "state_directory": str(campaign_dir),
        "ledger": str(ledger_path),
        "cache_directory": str(Path(cache_dir).expanduser().resolve()),
        "artifact_directory": (
            str(Path(artifact_dir).expanduser().resolve()) if artifact_dir else None
        ),
        "execution": {
            "jobs": jobs,
            "timeout_seconds": timeout,
            "stop_on_exact": stop_on_exact,
        },
        "sources": sorted(source_records, key=lambda item: str(item["path"])),
        "experiment": experiment,
    }
    _write_json_atomic(manifest_path, manifest)
    return manifest_path, ledger_path, manifest


def finish_manifest(
    path: str | Path,
    *,
    results: int,
    prepared: int,
    exact: bool,
    interrupted: bool = False,
) -> dict[str, Any]:
    """Atomically record the terminal state of a campaign invocation."""

    manifest_path = Path(path)
    manifest = load_manifest(manifest_path)
    manifest["updated_at_unix"] = time.time()
    manifest["status"] = (
        "interrupted" if interrupted else "exact" if exact else "complete"
    )
    manifest["last_run"] = {
        "results": results,
        "prepared": prepared,
        "exact": exact,
        "interrupted": interrupted,
    }
    _write_json_atomic(manifest_path, manifest)
    return manifest


def update_hypothesis(path: str | Path, note: str) -> dict[str, Any]:
    """Persist the campaign's current reasoning without rewriting its ledger."""

    normalized = note.strip()
    if not normalized:
        raise ValueError("campaign hypothesis must not be empty")
    if len(normalized) > 4096:
        raise ValueError("campaign hypothesis exceeds 4096 characters")
    manifest_path = resolve_manifest(path)
    manifest = load_manifest(manifest_path)
    manifest["hypothesis"] = normalized
    manifest["updated_at_unix"] = time.time()
    _write_json_atomic(manifest_path, manifest)
    return manifest


def load_manifest(path: str | Path) -> dict[str, Any]:
    """Load and validate the durable campaign manifest envelope."""

    manifest_path = resolve_manifest(path)
    value = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or value.get("schema") != MANIFEST_SCHEMA:
        raise ValueError(f"not a {MANIFEST_SCHEMA} document: {manifest_path}")
    return value


def resolve_manifest(path: str | Path) -> Path:
    """Resolve either a manifest path or its containing campaign directory."""

    candidate = Path(path).expanduser().resolve()
    if candidate.is_dir():
        candidate = candidate / "manifest.json"
    if not candidate.is_file():
        raise FileNotFoundError(f"campaign manifest does not exist: {candidate}")
    return candidate


def find_manifest(
    selector: str | Path | None = None,
    *,
    state_root: str | Path = DEFAULT_STATE_ROOT,
) -> Path:
    """Resolve an explicit campaign or select the most recently updated one."""

    if selector is not None:
        candidate = Path(selector).expanduser()
        if candidate.exists():
            return resolve_manifest(candidate)
    root = Path(state_root).expanduser().resolve() / "campaigns"
    manifests = list(root.glob("*/manifest.json")) if root.is_dir() else []
    if selector is not None:
        text = str(selector)
        manifests = [
            item
            for item in manifests
            if item.parent.name == text
            or item.parent.name.startswith(text)
            or load_manifest(item)["identity"].startswith(text)
        ]
    if not manifests:
        detail = f" matching {selector!r}" if selector is not None else ""
        raise FileNotFoundError(f"no campaign manifest found{detail} under {root}")
    if len(manifests) > 1 and selector is not None:
        names = ", ".join(sorted(item.parent.name for item in manifests))
        raise ValueError(f"campaign selector {selector!r} is ambiguous: {names}")
    return max(manifests, key=lambda item: item.stat().st_mtime)


def read_ledger(path: str | Path) -> tuple[list[dict[str, Any]], list[str]]:
    """Read append-only records, tolerating only an interrupted final write."""

    ledger = Path(path)
    if not ledger.is_file():
        return [], []
    lines = ledger.read_text(encoding="utf-8").splitlines()
    records: list[dict[str, Any]] = []
    warnings: list[str] = []
    for index, line in enumerate(lines, 1):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError as error:
            if index == len(lines):
                warnings.append(
                    f"ignored interrupted final ledger record at line {index}: {error}"
                )
                continue
            raise ValueError(
                f"invalid campaign ledger JSON at line {index}: {error}"
            ) from None
        if not isinstance(value, dict):
            raise ValueError(f"campaign ledger line {index} is not an object")
        records.append(value)
    return records, warnings


def _comparison_key(comparison: Mapping[str, Any]) -> tuple[object, ...]:
    return (
        int(comparison.get("aligned_total", 1 << 30)),
        int(comparison.get("words", comparison.get("word_mismatches", 1 << 30))),
        int(comparison.get("norm", comparison.get("normalized_distance", 1 << 30))),
        str(comparison.get("candidate", "")),
    )


def _compact_record(record: Mapping[str, Any]) -> dict[str, Any]:
    comparison = record.get("comparison")
    compact_comparison: dict[str, Any] | None = None
    if isinstance(comparison, dict):
        keys = (
            "candidate",
            "exact",
            "structural_exact",
            "verdict",
            "aligned_total",
            "aligned_structural",
            "aligned_schedule",
            "aligned_register",
            "aligned_constant",
            "aligned_commutative",
            "words",
            "word_mismatches",
            "candidate_sha1",
            "candidate_sha256",
        )
        compact_comparison = {key: comparison.get(key) for key in keys}
    return {
        "source": record.get("source"),
        "returncode": record.get("returncode"),
        "cached": record.get("cached"),
        "duration_seconds": record.get("duration_seconds"),
        "cache_key": record.get("cache_key"),
        "comparison": compact_comparison,
        "experiment": record.get("experiment"),
        "region": record.get("region"),
    }


def build_status(manifest_path: str | Path) -> dict[str, Any]:
    """Build the compact cockpit report from a manifest and its ledger."""

    path = resolve_manifest(manifest_path)
    manifest = load_manifest(path)
    records, warnings = read_ledger(manifest["ledger"])
    successful = [
        record for record in records if isinstance(record.get("comparison"), dict)
    ]
    best_record = min(
        successful,
        key=lambda record: _comparison_key(record["comparison"]),
        default=None,
    )
    trajectory = []
    best_so_far: Mapping[str, Any] | None = None
    basins: dict[str, list[str]] = {}
    families: dict[str, list[dict[str, Any]]] = {}
    failures = []
    previous_basin: str | None = None
    basin_transitions: list[dict[str, Any]] = []
    for index, record in enumerate(records, 1):
        comparison = record.get("comparison")
        if isinstance(comparison, dict):
            if best_so_far is None or _comparison_key(comparison) < _comparison_key(
                best_so_far
            ):
                best_so_far = comparison
            sha = str(comparison.get("candidate_sha256", "unknown"))
            basins.setdefault(sha, []).append(str(record.get("source", "unknown")))
            experiment = record.get("experiment")
            if isinstance(experiment, dict):
                family = str(experiment.get("family", "unclassified"))
                families.setdefault(family, []).append(record)
            if previous_basin is not None and sha != previous_basin:
                basin_transitions.append(
                    {
                        "record": index,
                        "source": record.get("source"),
                        "from": previous_basin,
                        "to": sha,
                        "family": (
                            experiment.get("family")
                            if isinstance(experiment, dict)
                            else None
                        ),
                    }
                )
            previous_basin = sha
            trajectory.append(
                {
                    "record": index,
                    "source": record.get("source"),
                    "aligned_total": comparison.get("aligned_total"),
                    "words": comparison.get("words", comparison.get("word_mismatches")),
                    "verdict": comparison.get("verdict"),
                    "best_aligned_total": (
                        best_so_far.get("aligned_total") if best_so_far else None
                    ),
                    "region": record.get("region"),
                }
            )
        else:
            failures.append(
                {
                    "source": record.get("source"),
                    "returncode": record.get("returncode"),
                    "stderr": str(record.get("stderr", ""))[-2048:],
                }
            )
    represented = {
        str(record.get("cache_key")) for record in records if record.get("cache_key")
    }
    prepared = manifest.get("sources", [])
    remaining = [
        item
        for item in prepared
        if isinstance(item, dict) and str(item.get("cache_key")) not in represented
    ]
    basin_rows: list[dict[str, Any]] = [
        {
            "candidate_sha256": sha,
            "variant_count": len(sources),
            "sources": sources,
        }
        for sha, sources in basins.items()
    ]
    basin_rows.sort(
        key=lambda item: (
            -int(item["variant_count"]),
            str(item["candidate_sha256"]),
        )
    )
    family_rows = []
    for family, family_records in sorted(families.items()):
        family_best = min(
            family_records,
            key=lambda record: _comparison_key(record["comparison"]),
        )
        family_basins = {
            str(record["comparison"].get("candidate_sha256"))
            for record in family_records
        }
        parameter_sets = {
            json.dumps(
                (
                    record.get("experiment", {}).get("parameters", {})
                    if isinstance(record.get("experiment"), dict)
                    else {}
                ),
                sort_keys=True,
                separators=(",", ":"),
            )
            for record in family_records
        }
        decoded_parameter_sets = [
            json.loads(value) for value in sorted(parameter_sets)[:64]
        ]
        metadata = family_records[0].get("experiment")
        parameter_space = (
            metadata.get("parameter_space", {}) if isinstance(metadata, dict) else {}
        )
        family_rows.append(
            {
                "family": family,
                "tested_candidates": len(family_records),
                "tested_parameter_sets": len(parameter_sets),
                "tested_parameters": decoded_parameter_sets,
                "tested_parameters_truncated": len(parameter_sets) > 64,
                "declared_parameter_space": parameter_space,
                "object_basins": len(family_basins),
                "best": _compact_record(family_best),
                "conclusion": (
                    f"{len(parameter_sets)} tested assignment(s) from "
                    f"{json.dumps(parameter_space, sort_keys=True)} produced "
                    f"{len(family_basins)} object basin(s)"
                ),
            }
        )
    return {
        "schema": STATUS_SCHEMA,
        "manifest": display_path(path),
        "identity": manifest["identity"],
        "status": manifest["status"],
        "target": manifest["identity_inputs"]["target"],
        "symbol": manifest["identity_inputs"].get("symbol"),
        "prepared_candidates": len(prepared),
        "recorded_candidates": len(records),
        "remaining_candidates": len(remaining),
        "successful_candidates": len(successful),
        "failed_candidates": len(failures),
        "object_basins": basin_rows,
        "best": _compact_record(best_record) if best_record else None,
        "trajectory": trajectory,
        "basin_transitions": basin_transitions,
        "families": family_rows,
        "failures": failures,
        "warnings": warnings,
        "experiment": manifest.get("experiment"),
        "hypothesis": manifest.get("hypothesis"),
    }


def validate_resume(manifest_path: str | Path) -> dict[str, Any]:
    """Refuse resume if any identity-bearing external input has changed."""

    manifest = load_manifest(manifest_path)
    identity_inputs = manifest["identity_inputs"]
    target = Path(identity_inputs["target"]["path"])
    if not target.is_file():
        raise FileNotFoundError(f"campaign target no longer exists: {target}")
    actual_target = file_sha256(target)
    if actual_target != identity_inputs["target"]["sha256"]:
        raise ValueError("campaign target hash changed; start a new campaign")
    compile_info = identity_inputs["compile"]
    compile_cwd = Path(compile_info["working_directory"])
    if not compile_cwd.is_dir():
        raise FileNotFoundError(
            f"compiler working directory no longer exists: {compile_cwd}"
        )
    requested = compile_info["compiler"]["requested"]
    current_compiler = executable_identity([requested], cwd=compile_cwd)
    if current_compiler != compile_info["compiler"]:
        raise ValueError("compiler identity changed; start a new campaign")
    requested_objdump = identity_inputs["objdump"]["requested"]
    current_objdump = executable_identity([requested_objdump], cwd=compile_cwd)
    if current_objdump != identity_inputs["objdump"]:
        raise ValueError("objdump identity changed; start a new campaign")
    toolchain = identity_inputs.get("toolchain")
    if isinstance(toolchain, dict):
        report = toolchain_status(toolchain["directory"])
        manifest_path = Path(str(toolchain["manifest"]))
        if (
            not report["integrity"]
            or not manifest_path.is_file()
            or file_sha256(manifest_path) != toolchain["manifest_sha256"]
        ):
            raise ValueError("toolchain identity changed; start a new campaign")
    for source in manifest.get("sources", []):
        path = Path(source["path"])
        if not path.is_file():
            raise FileNotFoundError(f"campaign source no longer exists: {path}")
        if file_sha256(path) != source["sha256"]:
            raise ValueError(
                f"campaign source hash changed: {path}; start a new campaign"
            )
    return manifest


def remaining_sources(manifest: Mapping[str, Any]) -> list[str]:
    """Return only source paths not represented in the append-only ledger."""

    records, _ = read_ledger(str(manifest["ledger"]))
    represented = {
        str(record.get("cache_key")) for record in records if record.get("cache_key")
    }
    return [
        str(item["path"])
        for item in manifest.get("sources", [])
        if str(item.get("cache_key")) not in represented
    ]


def _bookends(items: list[Any], limit: int) -> tuple[list[Any], bool]:
    """Keep representative history without silently dropping its tail."""

    if len(items) <= limit:
        return list(items), False
    first = limit // 2
    return [*items[:first], *items[-(limit - first) :]], True


def bounded_export_status(status: dict[str, Any]) -> dict[str, Any]:
    """Bound shareable campaign collections and state every omitted count."""

    result = dict(status)
    bounds: dict[str, dict[str, Any]] = {}
    for name, limit in (
        ("trajectory", EXPORT_TRAJECTORY_LIMIT),
        ("basin_transitions", EXPORT_TRANSITION_LIMIT),
        ("failures", EXPORT_FAILURE_LIMIT),
    ):
        original = list(status.get(name, []))
        selected, truncated = _bookends(original, limit)
        result[name] = selected
        bounds[name] = {
            "total": len(original),
            "included": len(selected),
            "truncated": truncated,
        }

    basins = []
    omitted_basin_sources = 0
    for original in status.get("object_basins", []):
        basin = dict(original)
        sources = list(original.get("sources", []))
        selected, truncated = _bookends(sources, EXPORT_BASIN_SOURCE_LIMIT)
        basin["sources"] = selected
        basin["sources_total"] = len(sources)
        basin["sources_truncated"] = truncated
        omitted_basin_sources += len(sources) - len(selected)
        basins.append(basin)
    result["object_basins"] = basins
    bounds["object_basin_sources"] = {
        "total": sum(
            len(original.get("sources", []))
            for original in status.get("object_basins", [])
        ),
        "included": sum(len(basin["sources"]) for basin in basins),
        "truncated": omitted_basin_sources > 0,
    }
    result["export_bounds"] = bounds
    return result


def export_status(manifest_path: str | Path) -> dict[str, Any]:
    """Build a bounded, shareable campaign report."""

    status = bounded_export_status(build_status(manifest_path))
    return {
        "schema": EXPORT_SCHEMA,
        "generated_at_unix": time.time(),
        "campaign": status,
        "proof": (
            "Function-level object evidence only; run the project's link, ROM, "
            "and collateral checks before integration."
        ),
    }
