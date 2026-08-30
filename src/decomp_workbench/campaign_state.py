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
from .experiment_signals import required_signals_pass
from .model import display_path
from .toolchain import MANIFEST_NAME as TOOLCHAIN_MANIFEST_NAME
from .toolchain import toolchain_status

MANIFEST_SCHEMA = "decomp-workbench-campaign-manifest-v1"
STATUS_SCHEMA = "decomp-workbench-campaign-status-v1"
EXPORT_SCHEMA = "decomp-workbench-campaign-export-v1"
DEFAULT_STATE_ROOT = Path(".decomp-workbench")
SOURCE_RETENTION_POLICIES = frozenset({"leaders", "exact", "all", "none"})
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


def _write_bytes_atomic(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_bytes(payload)
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
    experiment: Mapping[str, Any] | None = None,
    compilation_envelope: Mapping[str, str] | None = None,
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
            "environment_mode": "sealed",
            "compiler": executable_identity(command, cwd=compile_cwd),
        },
        "objdump": executable_identity([objdump], cwd=compile_cwd),
    }
    if compilation_envelope:
        payload["compile"]["envelope"] = dict(sorted(compilation_envelope.items()))
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
    if experiment is not None:
        payload["experiment"] = dict(experiment)
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
    rank_by: str = "auto",
    retain_sources: str = "leaders",
) -> tuple[Path, Path, dict[str, Any]]:
    """Create or extend the one manifest for a reproducible campaign identity."""

    if retain_sources not in SOURCE_RETENTION_POLICIES:
        raise ValueError("source retention must be leaders, exact, all, or none")
    target_name = Path(identity_inputs["target"]["path"]).stem
    label = identity_inputs.get("symbol") or target_name
    root = Path(state_root).expanduser().resolve()
    campaign_dir = root / "campaigns" / f"{_slug(str(label))}-{identity[:12]}"
    manifest_path = campaign_dir / "manifest.json"
    ledger_path = (
        Path(ledger).expanduser().resolve() if ledger else campaign_dir / "ledger.jsonl"
    )
    now = time.time()
    source_records: list[dict[str, Any]] = []
    durable_state: dict[str, Any] = {}
    for candidate in candidates:
        digest = str(candidate.provenance["source_sha256"])
        suffix = candidate.source.suffix if candidate.source.suffix else ".c"
        staged = campaign_dir / "source-staging" / f"{digest}{suffix}"
        if not staged.is_file():
            _write_bytes_atomic(staged, candidate.source.read_bytes())
        if file_sha256(staged) != digest:
            raise ValueError(f"retained source hash mismatch: {staged}")
        source_records.append(
            {
                "path": str(candidate.source),
                "sha256": digest,
                "cache_key": candidate.cache_key,
                "staged_path": str(staged),
                "retained_path": None,
                "retention": "staged",
            }
        )
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
        previous_policy = manifest.get("execution", {}).get("retain_sources", "leaders")
        if previous_policy != retain_sources:
            raise ValueError(
                "campaign source retention policy changed; resume with "
                f"{previous_policy!r} or start a new campaign"
            )
        for item in source_records:
            key = str(item["cache_key"])
            if key in existing:
                prior = existing[key]
                item["retained_path"] = prior.get("retained_path")
                item["retention"] = prior.get("retention", "staged")
            existing[key] = item
        source_records = list(existing.values())
        created = manifest.get("created_at_unix", now)
        durable_state = {
            key: manifest[key]
            for key in ("hypothesis", "artifacts", "accepted")
            if key in manifest
        }
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
            "rank_by": rank_by,
            "retain_sources": retain_sources,
        },
        "sources": sorted(source_records, key=lambda item: str(item["path"])),
        "experiment": experiment,
        **durable_state,
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
    control_invalid: bool = False,
) -> dict[str, Any]:
    """Atomically record the terminal state of a campaign invocation."""

    manifest_path = Path(path)
    manifest = load_manifest(manifest_path)
    manifest["updated_at_unix"] = time.time()
    manifest["status"] = (
        "control-invalid"
        if control_invalid
        else "interrupted"
        if interrupted
        else "exact"
        if exact
        else "complete"
    )
    manifest["last_run"] = {
        "results": results,
        "prepared": prepared,
        "exact": exact,
        "interrupted": interrupted,
        "control_invalid": control_invalid,
    }
    _write_json_atomic(manifest_path, manifest)
    return manifest


def record_control_preflight(
    path: str | Path, report: Mapping[str, Any]
) -> dict[str, Any]:
    """Persist one immutable-by-campaign control receipt before ordinary work."""

    manifest_path = resolve_manifest(path)
    manifest = load_manifest(manifest_path)
    manifest["control_preflight"] = dict(report)
    manifest["updated_at_unix"] = time.time()
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
    require_explicit_when_ambiguous: bool = False,
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
    if selector is None and len(manifests) > 1 and require_explicit_when_ambiguous:
        names = ", ".join(sorted(item.parent.name for item in manifests))
        raise ValueError(
            "more than one campaign exists; select one explicitly before a "
            f"mutating action: {names}"
        )
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


def _alignment_comparable(comparison: Mapping[str, Any]) -> bool:
    """Read the explicit flag, with a safe fallback for older ledgers."""

    if "alignment_comparable" in comparison:
        return bool(comparison["alignment_comparable"])
    return int(comparison.get("aligned_gaps", 0) or 0) == 0


def _effective_rank_by(
    records: list[dict[str, Any]], *, requested: str
) -> tuple[str, bool]:
    """Resolve ``auto`` once for the whole persisted candidate population."""

    unsafe = any(
        not _alignment_comparable(comparison)
        for record in records
        if isinstance((comparison := record.get("comparison")), dict)
    )
    if requested == "auto":
        return ("words" if unsafe else "aligned_total"), unsafe
    return requested, unsafe


def _comparison_key(
    comparison: Mapping[str, Any], *, ranked_by: str = "aligned_total"
) -> tuple[object, ...]:
    words = int(comparison.get("words", comparison.get("word_mismatches", 1 << 30)))
    aligned = int(comparison.get("aligned_total", 1 << 30))
    unknown = comparison.get("unknown_relocations", [])
    unknown_count = len(unknown) if isinstance(unknown, list) else 0
    relocation_metadata = int(
        comparison.get(
            "reloc_meta", comparison.get("relocation_metadata_mismatches", 0)
        )
    )
    candidate = str(comparison.get("candidate", ""))
    if ranked_by == "temp-prefix":
        return _temp_prefix_key(comparison)
    if ranked_by == "words":
        return (
            words,
            int(comparison.get("raw_word_mismatches", words)),
            unknown_count,
            relocation_metadata,
            int(comparison.get("opcodes", comparison.get("opcode_mismatches", 0))),
            aligned,
            abs(int(comparison.get("instruction_delta", 0))),
            candidate,
        )
    return (
        aligned,
        words,
        unknown_count,
        relocation_metadata,
        int(comparison.get("norm", comparison.get("normalized_distance", 1 << 30))),
        int(comparison.get("registers", comparison.get("register_mismatches", 0))),
        abs(int(comparison.get("instruction_delta", 0))),
        candidate,
    )


def _record_key(
    record: Mapping[str, Any], *, ranked_by: str = "aligned_total"
) -> tuple[object, ...]:
    """Mirror the live campaign's signal, region, and metric ordering."""

    comparison = record.get("comparison")
    signals = record.get("signals", [])
    signal_key = (
        not required_signals_pass(signals if isinstance(signals, list) else []),
    )
    region = record.get("region")
    region_key: tuple[object, ...] = ()
    if isinstance(region, dict):
        region_key = (
            not bool(region.get("exact")),
            int(region.get("selected_mismatches", 1 << 30)),
            int(region.get("outside_mismatches", 1 << 30)),
        )
    metric = (
        _comparison_key(comparison, ranked_by=ranked_by)
        if isinstance(comparison, dict)
        else ()
    )
    return (
        not isinstance(comparison, dict),
        *signal_key,
        *region_key,
        metric,
        str(record.get("source", "")),
    )


def _retention_leaders(records: list[dict[str, Any]], *, ranked_by: str) -> set[str]:
    """Return cache keys that advanced score, exactness, or a mechanism signal."""

    leaders: set[str] = set()
    best: tuple[object, ...] | None = None
    signal_state: dict[str, str] = {}
    for record in records:
        key = str(record.get("cache_key", ""))
        comparison = record.get("comparison")
        if key and isinstance(comparison, dict):
            rank = _record_key(record, ranked_by=ranked_by)
            if best is None or rank < best:
                leaders.add(key)
                best = rank
            if bool(comparison.get("exact")):
                leaders.add(key)
        changed_signal = False
        for signal in record.get("signals", []):
            if not isinstance(signal, dict) or not isinstance(signal.get("id"), str):
                continue
            signal_id = str(signal["id"])
            status = str(signal.get("status", "UNKNOWN"))
            if signal_state.get(signal_id) != status:
                changed_signal = True
            signal_state[signal_id] = status
        if key and changed_signal:
            leaders.add(key)
    return leaders


def finalize_source_retention(manifest_path: str | Path) -> dict[str, Any]:
    """Promote the requested durable source set and prune staging copies.

    Unrun candidates always remain staged so an exact stop or interruption
    cannot make a later resume impossible.
    """

    path = resolve_manifest(manifest_path)
    manifest = load_manifest(path)
    records, _ = read_ledger(manifest["ledger"])
    policy = str(manifest.get("execution", {}).get("retain_sources", "leaders"))
    represented = {
        str(record.get("cache_key")) for record in records if record.get("cache_key")
    }
    if policy == "all":
        keep = {
            str(item.get("cache_key"))
            for item in manifest.get("sources", [])
            if isinstance(item, dict)
        }
    elif policy == "exact":
        keep = {
            str(record.get("cache_key"))
            for record in records
            if isinstance(record.get("comparison"), dict)
            and bool(record["comparison"].get("exact"))
        }
    elif policy == "leaders":
        requested = str(manifest.get("execution", {}).get("rank_by", "auto"))
        ranked_by, _ = _effective_rank_by(records, requested=requested)
        keep = _retention_leaders(records, ranked_by=ranked_by)
    else:
        keep = set()
    keep.update(
        str(item.get("cache_key"))
        for item in manifest.get("sources", [])
        if isinstance(item, dict) and str(item.get("cache_key")) not in represented
    )

    retained_directory = path.parent / "sources"
    kept_stage_paths: set[Path] = set()
    for item in manifest.get("sources", []):
        if not isinstance(item, dict):
            continue
        staged_value = item.get("staged_path")
        staged = Path(str(staged_value)) if staged_value else None
        key = str(item.get("cache_key", ""))
        if key not in keep:
            continue
        suffix = Path(str(item.get("path", "source.c"))).suffix or ".c"
        retained = retained_directory / f"{item['sha256']}{suffix}"
        retained.parent.mkdir(parents=True, exist_ok=True)
        if not retained.is_file() and staged is not None and staged.is_file():
            os.replace(staged, retained)
        if not retained.is_file() or file_sha256(retained) != item.get("sha256"):
            raise ValueError(f"durable source retention failed: {retained}")
        item["retained_path"] = str(retained)
        item["retention"] = "pending" if key not in represented else "retained"
        if staged is not None:
            kept_stage_paths.add(staged)

    retained_paths = {
        Path(str(item["retained_path"]))
        for item in manifest.get("sources", [])
        if isinstance(item, dict) and item.get("retained_path")
    }
    for item in manifest.get("sources", []):
        if not isinstance(item, dict):
            continue
        staged_value = item.get("staged_path")
        staged = Path(str(staged_value)) if staged_value else None
        if (
            staged is not None
            and staged.is_file()
            and staged not in kept_stage_paths
            and staged not in retained_paths
        ):
            staged.unlink()
            item["retention"] = "not-retained"
            item["staged_path"] = None
    manifest["updated_at_unix"] = time.time()
    _write_json_atomic(path, manifest)
    return manifest


def durable_source_path(source_record: Mapping[str, Any]) -> Path:
    """Return a source copy whose content still matches the manifest."""

    expected = str(source_record.get("sha256", ""))
    for field in ("retained_path", "staged_path", "path"):
        value = source_record.get(field)
        if not value:
            continue
        candidate = Path(str(value))
        if candidate.is_file() and file_sha256(candidate) == expected:
            return candidate
    raise FileNotFoundError(
        "campaign source and its retained copy are unavailable or changed: "
        f"{source_record.get('path')}"
    )


def _temp_prefix_key(comparison: Mapping[str, Any]) -> tuple[object, ...]:
    """Rank the allocation-stable population by how late temps diverge."""

    temp = comparison.get("temp_prefix_exact")
    instructions = int(comparison.get("target_instructions", 0))
    effective = instructions + 1 if temp is None else int(temp)
    return (
        comparison.get("alignment_method") != "positional-opcode",
        not bool(comparison.get("pool_exact", False)),
        -effective,
        int(comparison.get("words", comparison.get("word_mismatches", 1 << 30))),
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
            "pool_exact",
            "pool_prefix_exact",
            "temp_prefix_exact",
            "first_temp_divergence",
            "first_divergent_row",
            "alignment_method",
            "words",
            "word_mismatches",
            "raw",
            "raw_word_mismatches",
            "relocation_target_mismatches",
            "relocation_metadata_mismatches",
            "candidate_sha1",
            "candidate_sha256",
        )
        compact_comparison = {key: comparison.get(key) for key in keys}
    return {
        "recorded_at_unix": record.get("recorded_at_unix"),
        "source": record.get("source"),
        "returncode": record.get("returncode"),
        "cached": record.get("cached"),
        "duration_seconds": record.get("duration_seconds"),
        "cache_key": record.get("cache_key"),
        "object_sha256": record.get("object_sha256"),
        "source_sha256": (
            record.get("provenance", {}).get("source_sha256")
            if isinstance(record.get("provenance"), dict)
            else None
        ),
        "comparison": compact_comparison,
        "experiment": record.get("experiment"),
        "region": record.get("region"),
        "signals": record.get("signals", []),
    }


def _recover_experiment_metadata(
    manifest: Mapping[str, Any], records: list[dict[str, Any]]
) -> tuple[list[dict[str, Any]], int]:
    """Join legacy ledger rows back to experiment metadata in the manifest.

    Experiment manifests are copied into campaign manifests, including absolute
    candidate paths and the prepared source cache keys.  Older or stale CLI
    entry points could therefore leave ``experiment: null`` in the ledger even
    though the durable campaign manifest still has enough information to make
    the result interpretable.  Recover that relationship by cache key rather
    than by the display path recorded in the ledger, which depends on the
    directory from which the campaign was launched.
    """

    experiment = manifest.get("experiment")
    sources = manifest.get("sources")
    if not isinstance(experiment, dict) or not isinstance(sources, list):
        return records, 0
    candidates = experiment.get("candidates")
    if not isinstance(candidates, list):
        return records, 0
    parameters_by_source = {
        str(candidate["source"]): candidate.get("parameters", {})
        for candidate in candidates
        if isinstance(candidate, dict) and "source" in candidate
    }
    source_by_key = {
        str(source["cache_key"]): str(source["path"])
        for source in sources
        if isinstance(source, dict) and source.get("cache_key") and source.get("path")
    }
    recovered = 0
    enriched: list[dict[str, Any]] = []
    for record in records:
        if isinstance(record.get("experiment"), dict):
            enriched.append(record)
            continue
        source = source_by_key.get(str(record.get("cache_key", "")))
        provenance = record.get("provenance")
        if source is None and isinstance(provenance, dict):
            provenance_source = provenance.get("source")
            if isinstance(provenance_source, str):
                source = provenance_source
        if source not in parameters_by_source:
            enriched.append(record)
            continue
        restored = dict(record)
        restored["experiment"] = {
            "schema": experiment.get("schema"),
            "family": experiment.get("family"),
            "parameters": parameters_by_source[source],
            "parameter_space": experiment.get("parameters", {}),
            "baseline": experiment.get("baseline"),
            "manifest": experiment.get("path"),
        }
        enriched.append(restored)
        recovered += 1
    return enriched, recovered


def _homologous_guidance(
    manifest: Mapping[str, Any],
    successful: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Turn measured one-parameter prefix gains into sibling-branch probes.

    Homology is declared by the generator, never guessed from parameter names.
    A recommendation requires an observed pair that differs in exactly one
    homologous parameter while every other parameter is held fixed, and it is
    emitted only when the corresponding sibling assignment has not been run.
    """

    experiment = manifest.get("experiment")
    if not isinstance(experiment, dict):
        return []
    groups = experiment.get("homologous_parameters", [])
    if not isinstance(groups, list):
        return []
    observations: list[tuple[dict[str, Any], dict[str, Any], dict[str, Any]]] = []
    tested: set[str] = set()
    for record in successful:
        metadata = record.get("experiment")
        comparison = record.get("comparison")
        if not isinstance(metadata, dict) or not isinstance(comparison, dict):
            continue
        parameters = metadata.get("parameters")
        if not isinstance(parameters, dict):
            continue
        tested.add(json.dumps(parameters, sort_keys=True, separators=(",", ":")))
        observations.append((record, parameters, comparison))

    def prefix_value(comparison: Mapping[str, Any]) -> int:
        value = comparison.get("temp_prefix_exact")
        if value is None:
            # A lane that never diverges is stronger than every finite row.
            return 1 << 30
        return int(value)

    guidance: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw_group in groups:
        if not isinstance(raw_group, list) or len(raw_group) < 2:
            continue
        group = [str(name) for name in raw_group]
        for poorer_record, poorer, poorer_comparison in observations:
            for better_record, better, better_comparison in observations:
                changed = {
                    name
                    for name in set(poorer) | set(better)
                    if poorer.get(name) != better.get(name)
                }
                if len(changed) != 1:
                    continue
                changed_name = next(iter(changed))
                if changed_name not in group:
                    continue
                before = prefix_value(poorer_comparison)
                after = prefix_value(better_comparison)
                if after <= before:
                    continue
                winning_value = better.get(changed_name)
                for sibling in group:
                    if sibling == changed_name or poorer.get(sibling) == winning_value:
                        continue
                    suggested = dict(poorer)
                    suggested[sibling] = winning_value
                    serialized = json.dumps(
                        suggested, sort_keys=True, separators=(",", ":")
                    )
                    if serialized in tested or serialized in seen:
                        continue
                    seen.add(serialized)
                    before_label: object = "exact" if before == 1 << 30 else before
                    after_label: object = "exact" if after == 1 << 30 else after
                    guidance.append(
                        {
                            "group": group,
                            "evidence_parameter": changed_name,
                            "sibling_parameter": sibling,
                            "winning_value": winning_value,
                            "prefix_before": (None if before == 1 << 30 else before),
                            "prefix_after": None if after == 1 << 30 else after,
                            "words_before": poorer_comparison.get(
                                "words", poorer_comparison.get("word_mismatches")
                            ),
                            "words_after": better_comparison.get(
                                "words", better_comparison.get("word_mismatches")
                            ),
                            "evidence_sources": [
                                poorer_record.get("source"),
                                better_record.get("source"),
                            ],
                            "suggested_parameters": suggested,
                            "reason": (
                                f"changing {changed_name} alone moved the first "
                                f"temp divergence from {before_label} "
                                f"to {after_label}; "
                                f"test the same value at homologous {sibling}"
                            ),
                        }
                    )
    return guidance


def build_status(manifest_path: str | Path) -> dict[str, Any]:
    """Build the compact cockpit report from a manifest and its ledger."""

    path = resolve_manifest(manifest_path)
    manifest = load_manifest(path)
    records, warnings = read_ledger(manifest["ledger"])
    records, recovered_metadata = _recover_experiment_metadata(manifest, records)
    if recovered_metadata:
        warnings.append(
            f"recovered experiment metadata for {recovered_metadata} ledger "
            "record(s) from the campaign manifest"
        )
    successful = [
        record for record in records if isinstance(record.get("comparison"), dict)
    ]
    requested_rank_by = str(manifest.get("execution", {}).get("rank_by", "auto"))
    ranked_by, alignment_ranking_unsafe = _effective_rank_by(
        successful, requested=requested_rank_by
    )
    best_record = min(
        successful,
        key=lambda record: _record_key(record, ranked_by=ranked_by),
        default=None,
    )
    best_temp_prefix_record = min(
        successful,
        key=lambda record: _temp_prefix_key(record["comparison"]),
        default=None,
    )
    trajectory = []
    mechanism_trajectory: list[dict[str, Any]] = []
    signal_state: dict[str, str] = {}
    best_so_far: Mapping[str, Any] | None = None
    best_aligned_total_so_far: int | None = None
    best_words_so_far: int | None = None
    basins: dict[str, list[str]] = {}
    basin_signals: dict[str, dict[str, set[str]]] = {}
    families: dict[str, list[dict[str, Any]]] = {}
    failures = []
    previous_basin: str | None = None
    basin_transitions: list[dict[str, Any]] = []
    for index, record in enumerate(records, 1):
        comparison = record.get("comparison")
        if isinstance(comparison, dict):
            if best_so_far is None or _record_key(
                record, ranked_by=ranked_by
            ) < _record_key(best_so_far, ranked_by=ranked_by):
                best_so_far = record
            aligned_total = int(comparison.get("aligned_total", 1 << 30))
            words_value = comparison.get(
                "words", comparison.get("word_mismatches", 1 << 30)
            )
            words = int(words_value) if words_value is not None else 1 << 30
            best_aligned_total_so_far = (
                aligned_total
                if best_aligned_total_so_far is None
                else min(best_aligned_total_so_far, aligned_total)
            )
            best_words_so_far = (
                words if best_words_so_far is None else min(best_words_so_far, words)
            )
            sha = str(comparison.get("candidate_sha256", "unknown"))
            basins.setdefault(sha, []).append(str(record.get("source", "unknown")))
            for signal in record.get("signals", []):
                if isinstance(signal, dict) and isinstance(signal.get("id"), str):
                    basin_signals.setdefault(sha, {}).setdefault(
                        str(signal["id"]), set()
                    ).add(str(signal.get("status", "UNKNOWN")))
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
                    "pool_exact": comparison.get("pool_exact"),
                    "pool_prefix_exact": comparison.get("pool_prefix_exact"),
                    "temp_prefix_exact": comparison.get("temp_prefix_exact"),
                    "first_temp_divergence": comparison.get("first_temp_divergence"),
                    "first_divergent_row": comparison.get("first_divergent_row"),
                    "alignment_method": comparison.get("alignment_method"),
                    "best_aligned_total": best_aligned_total_so_far,
                    "best_words": best_words_so_far,
                    "region": record.get("region"),
                }
            )
            signals = record.get("signals", [])
            if isinstance(signals, list):
                for signal in signals:
                    if not isinstance(signal, dict) or not isinstance(
                        signal.get("id"), str
                    ):
                        continue
                    signal_id = str(signal["id"])
                    status = str(signal.get("status", "UNKNOWN"))
                    previous = signal_state.get(signal_id)
                    if previous != status:
                        mechanism_trajectory.append(
                            {
                                "record": index,
                                "source": record.get("source"),
                                "signal": signal_id,
                                "required": bool(signal.get("required")),
                                "from": previous,
                                "to": status,
                            }
                        )
                    signal_state[signal_id] = status
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
            "signals": {
                signal: sorted(statuses)
                for signal, statuses in sorted(basin_signals.get(sha, {}).items())
            },
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
            key=lambda record: _record_key(record, ranked_by=ranked_by),
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
    homologous_guidance = _homologous_guidance(manifest, successful)
    experiment_definition = manifest.get("experiment")
    control_preflight = manifest.get(
        "control_preflight",
        {"status": "NOT DECLARED", "passed": True, "receipts": []},
    )
    coverage: dict[str, Any]
    conclusion_label: str
    if isinstance(experiment_definition, dict):
        parameter_space = experiment_definition.get("parameters", {})
        declared = 1
        if isinstance(parameter_space, dict):
            for choices in parameter_space.values():
                if isinstance(choices, list):
                    declared *= len(choices)
                else:
                    declared = 0
                    break
        else:
            declared = 0
        visited_assignments = {
            json.dumps(
                record.get("experiment", {}).get("parameters", {}),
                sort_keys=True,
                separators=(",", ":"),
            )
            for record in records
            if isinstance(record.get("experiment"), dict)
        }
        declaration = experiment_definition.get("coverage", {})
        excluded = (
            int(declaration.get("excluded", 0)) if isinstance(declaration, dict) else 0
        )
        visited = len(visited_assignments)
        unvisited = max(0, declared - visited - excluded) if declared else None
        if manifest.get("status") == "control-invalid" or not bool(
            control_preflight.get("passed", True)
            if isinstance(control_preflight, dict)
            else True
        ):
            conclusion_label = "control-invalid"
        elif manifest.get("status") == "interrupted":
            conclusion_label = "partial-interrupted"
        elif not declared:
            conclusion_label = "coverage-unknown"
        elif visited + excluded >= declared:
            conclusion_label = "exhaustive-over-declared-space"
        else:
            conclusion_label = "sampled-over-declared-space"
        coverage = {
            "declared_assignments": declared or None,
            "visited_assignments": visited,
            "excluded_assignments": excluded,
            "unvisited_assignments": unvisited,
            "method": (
                declaration.get("method", "explicit-candidates")
                if isinstance(declaration, dict)
                else "explicit-candidates"
            ),
            "sampling": (
                declaration.get("sampling") if isinstance(declaration, dict) else None
            ),
            "exclusion_reason": (
                declaration.get("exclusion_reason")
                if isinstance(declaration, dict)
                else None
            ),
            "conclusion": conclusion_label,
        }
    else:
        conclusion_label = "coverage-unknown"
        coverage = {
            "declared_assignments": None,
            "visited_assignments": len(records),
            "excluded_assignments": 0,
            "unvisited_assignments": None,
            "method": "unmeasured",
            "sampling": None,
            "exclusion_reason": None,
            "conclusion": conclusion_label,
        }
    for family_row in family_rows:
        family_row["coverage"] = coverage
        family_row["conclusion_label"] = conclusion_label
    source_records = [item for item in prepared if isinstance(item, dict)]
    source_retention = {
        "policy": manifest.get("execution", {}).get("retain_sources", "leaders"),
        "retained": sum(
            1 for item in source_records if item.get("retention") == "retained"
        ),
        "pending": sum(
            1 for item in source_records if item.get("retention") == "pending"
        ),
        "not_retained": sum(
            1 for item in source_records if item.get("retention") == "not-retained"
        ),
    }
    return {
        "schema": STATUS_SCHEMA,
        "manifest": display_path(path),
        "identity": manifest["identity"],
        "status": manifest["status"],
        "rank_by": requested_rank_by,
        "ranked_by": ranked_by,
        "alignment_ranking_unsafe": alignment_ranking_unsafe,
        "target": manifest["identity_inputs"]["target"],
        "symbol": manifest["identity_inputs"].get("symbol"),
        "prepared_candidates": len(prepared),
        "recorded_candidates": len(records),
        "remaining_candidates": len(remaining),
        "successful_candidates": len(successful),
        "failed_candidates": len(failures),
        "object_basins": basin_rows,
        "best": _compact_record(best_record) if best_record else None,
        "best_temp_prefix": (
            _compact_record(best_temp_prefix_record)
            if best_temp_prefix_record
            else None
        ),
        "trajectory": trajectory,
        "acceptance_trajectory": trajectory,
        "mechanism_trajectory": mechanism_trajectory,
        "basin_transitions": basin_transitions,
        "families": family_rows,
        "homologous_guidance": homologous_guidance,
        "failures": failures,
        "warnings": warnings,
        "experiment": manifest.get("experiment"),
        "controls": control_preflight,
        "coverage": coverage,
        "conclusion_label": conclusion_label,
        "hypothesis": manifest.get("hypothesis"),
        "artifacts": {
            role: value.get("id")
            for role, value in (manifest.get("artifacts") or {}).items()
            if isinstance(value, dict) and isinstance(value.get("id"), str)
        },
        "accepted": manifest.get("accepted"),
        "source_retention": source_retention,
    }


def validate_resume(
    manifest_path: str | Path, *, allow_retained_sources: bool = False
) -> dict[str, Any]:
    """Refuse use when an identity-bearing external input is unavailable.

    Resume requires the original path because source paths can affect compiler
    output. Finish/package may use an immutable retained copy and then let the
    fresh comparison prove whether a changed path matters.
    """

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
    experiment = identity_inputs.get("experiment")
    if isinstance(experiment, dict):
        from .experiments import load_experiment

        experiment_path = experiment.get("path")
        if not isinstance(experiment_path, str):
            raise ValueError("campaign experiment identity is incomplete")
        current_experiment = load_experiment(experiment_path).identity_receipt()
        if current_experiment != experiment:
            raise ValueError(
                "experiment controls/signals/coverage changed; start a new campaign"
            )
    for source in manifest.get("sources", []):
        path = Path(source["path"])
        if path.is_file() and file_sha256(path) == source["sha256"]:
            continue
        if allow_retained_sources:
            durable_source_path(source)
            continue
        if not path.is_file():
            raise FileNotFoundError(
                f"campaign source no longer exists at its identity-bearing "
                f"path: {path}; the retained copy remains available for finish "
                "and package, but resume could change path-sensitive output"
            )
        raise ValueError(f"campaign source hash changed: {path}; start a new campaign")
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
        ("mechanism_trajectory", EXPORT_TRANSITION_LIMIT),
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
    result["acceptance_trajectory"] = result["trajectory"]

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
