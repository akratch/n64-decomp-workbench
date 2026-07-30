"""Real-copy external toolchain directories with explicit calibration state."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import time
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from .campaign import file_sha256
from .fidelity import compare_object_fidelity
from .scheduler import parse_scheduler_trace

TOOLCHAIN_SCHEMA = "decomp-workbench-toolchain-v1"
MANIFEST_NAME = "workbench-toolchain.json"
CALIBRATION_GATES = (
    "real_copy",
    "fidelity",
    "positive_control",
    "unedited_replay",
    "collateral",
    "project_output",
)


def _tree_inventory(root: Path) -> tuple[list[dict[str, Any]], str]:
    entries = []
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise ValueError(f"toolchain contains a symlink after copy: {path}")
        if path.is_dir():
            continue
        if not path.is_file():
            raise ValueError(f"toolchain contains unsupported filesystem node: {path}")
        entries.append(
            {
                "path": path.relative_to(root).as_posix(),
                "bytes": path.stat().st_size,
                "sha256": file_sha256(path),
            }
        )
    digest = hashlib.sha256(
        json.dumps(entries, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return entries, digest


def _parse_replacements(
    values: Mapping[str, str | Path],
) -> dict[str, Path]:
    result = {}
    for relative, source_value in values.items():
        relative_path = Path(relative)
        if (
            relative_path.is_absolute()
            or ".." in relative_path.parts
            or relative_path == Path(".")
        ):
            raise ValueError(
                f"replacement destination must be a relative file path: {relative!r}"
            )
        source = Path(source_value).expanduser().resolve()
        if not source.is_file():
            raise FileNotFoundError(f"replacement binary does not exist: {source}")
        result[relative_path.as_posix()] = source
    return result


def _write_manifest(path: Path, manifest: dict[str, Any]) -> None:
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def _scheduler_positive_control(path: str | Path) -> dict[str, Any]:
    source = Path(path).expanduser().resolve()
    events, _ = parse_scheduler_trace(source.read_text(encoding="utf-8"))
    ties = sum(event.ready > 1 for event in events)
    return {
        "path": str(source),
        "sha256": file_sha256(source),
        "events": len(events),
        "ready_set_ties": ties,
        "pass": bool(events) and ties > 0,
    }


def _exact_file_pair(expected: str | Path, actual: str | Path) -> dict[str, Any]:
    expected_path = Path(expected).expanduser().resolve()
    actual_path = Path(actual).expanduser().resolve()
    if not expected_path.is_file():
        raise FileNotFoundError(
            f"expected project output does not exist: {expected_path}"
        )
    if not actual_path.is_file():
        raise FileNotFoundError(f"actual project output does not exist: {actual_path}")
    expected_hash = file_sha256(expected_path)
    actual_hash = file_sha256(actual_path)
    return {
        "expected": str(expected_path),
        "actual": str(actual_path),
        "expected_sha256": expected_hash,
        "actual_sha256": actual_hash,
        "pass": expected_hash == actual_hash,
    }


def initialize_toolchain(
    destination: str | Path,
    *,
    base: str | Path,
    replacements: Mapping[str, str | Path],
    fidelity_pairs: Sequence[tuple[str | Path, str | Path]] | None = None,
    scheduler_positive_log: str | Path | None = None,
    objdump: str | None = None,
) -> dict[str, Any]:
    """Materialize a real-copy toolchain and record every externally owned hash."""

    base_path = Path(base).expanduser().resolve()
    output = Path(destination).expanduser().resolve()
    if not base_path.is_dir():
        raise NotADirectoryError(f"base toolchain is not a directory: {base_path}")
    if output.exists():
        raise FileExistsError(f"refusing to overwrite toolchain: {output}")
    if base_path == output or base_path in output.parents:
        raise ValueError("destination must not be inside the base toolchain")
    replacement_paths = _parse_replacements(replacements)
    owns_output = False
    try:
        # Reserve the exact destination before copying. This closes the race
        # between the existence check and ``copytree`` and, more importantly,
        # means failure cleanup can only remove a directory created here.
        output.mkdir(parents=True)
        owns_output = True
        # ``symlinks=False`` deliberately dereferences the source tree. IDO
        # layouts commonly contain links, while the resulting toolchain must
        # contain ordinary files so path-sensitive driver behavior is honest.
        shutil.copytree(base_path, output, symlinks=False, dirs_exist_ok=True)
        _, base_digest = _tree_inventory(output)
        installed = {}
        for relative, source in replacement_paths.items():
            target = (output / relative).resolve()
            if output not in target.parents:
                raise ValueError(
                    f"replacement destination escapes toolchain: {relative}"
                )
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
            installed[relative] = {
                "source": str(source),
                "source_sha256": file_sha256(source),
                "installed_sha256": file_sha256(target),
            }
        fidelity = [
            compare_object_fidelity(stock, instrumented, objdump=objdump)
            for stock, instrumented in (fidelity_pairs or [])
        ]
        scheduler_positive = (
            _scheduler_positive_control(scheduler_positive_log)
            if scheduler_positive_log
            else None
        )
        entries, installed_digest = _tree_inventory(output)
        gates = {
            "real_copy": True,
            "fidelity": bool(fidelity) and all(item["pass"] for item in fidelity),
            "positive_control": bool(scheduler_positive and scheduler_positive["pass"]),
            "unedited_replay": False,
            "collateral": False,
            "project_output": False,
        }
        manifest = {
            "schema": TOOLCHAIN_SCHEMA,
            "created_at_unix": time.time(),
            "base": str(base_path),
            "base_inventory_sha256": base_digest,
            "installed_inventory_sha256": installed_digest,
            "files": len(entries),
            "replacements": installed,
            "fidelity_reports": fidelity,
            "scheduler_positive_control": scheduler_positive,
            "gates": gates,
            "claim": "ready" if all(gates.values()) else "uncalibrated",
        }
        _write_manifest(output / MANIFEST_NAME, manifest)
    except BaseException:
        if owns_output:
            shutil.rmtree(output)
        raise
    return {**manifest, "directory": str(output)}


def calibrate_toolchain(
    path: str | Path,
    *,
    unedited_replay_pairs: Sequence[tuple[str | Path, str | Path]] = (),
    collateral_pairs: Sequence[tuple[str | Path, str | Path]] = (),
    project_output_pairs: Sequence[tuple[str | Path, str | Path]] = (),
    scheduler_positive_log: str | Path | None = None,
    objdump: str | None = None,
) -> dict[str, Any]:
    """Run explicit calibration cells and atomically update their evidence."""

    root = Path(path).expanduser().resolve()
    status = toolchain_status(root)
    if not status["integrity"]:
        raise ValueError("toolchain integrity failed; restore or reinitialize it")
    manifest_path = root / MANIFEST_NAME
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    evidence = dict(manifest.get("calibration_evidence", {}))

    def fidelity_reports(
        pairs: Sequence[tuple[str | Path, str | Path]],
    ) -> list[dict[str, Any]]:
        return [
            compare_object_fidelity(stock, candidate, objdump=objdump)
            for stock, candidate in pairs
        ]

    if unedited_replay_pairs:
        reports = fidelity_reports(unedited_replay_pairs)
        evidence["unedited_replay"] = reports
        manifest["gates"]["unedited_replay"] = all(
            bool(report["pass"]) for report in reports
        )
    if collateral_pairs:
        reports = fidelity_reports(collateral_pairs)
        evidence["collateral"] = reports
        manifest["gates"]["collateral"] = all(
            bool(report["pass"]) for report in reports
        )
    if project_output_pairs:
        reports = [
            _exact_file_pair(expected, actual)
            for expected, actual in project_output_pairs
        ]
        evidence["project_output"] = reports
        manifest["gates"]["project_output"] = all(
            bool(report["pass"]) for report in reports
        )
    if scheduler_positive_log is not None:
        report = _scheduler_positive_control(scheduler_positive_log)
        manifest["scheduler_positive_control"] = report
        evidence["positive_control"] = report
        manifest["gates"]["positive_control"] = bool(report["pass"])
    if not any(
        (
            unedited_replay_pairs,
            collateral_pairs,
            project_output_pairs,
            scheduler_positive_log,
        )
    ):
        raise ValueError("calibration requires at least one evidence input")

    manifest["calibration_evidence"] = evidence
    manifest["updated_at_unix"] = time.time()
    manifest["claim"] = (
        "ready"
        if all(manifest["gates"].get(gate, False) for gate in CALIBRATION_GATES)
        else "uncalibrated"
    )
    _write_manifest(manifest_path, manifest)
    return toolchain_status(root)


def toolchain_status(path: str | Path) -> dict[str, Any]:
    """Verify the installed copy and print no claim stronger than its gates."""

    root = Path(path).expanduser().resolve()
    manifest_path = root / MANIFEST_NAME
    if not manifest_path.is_file():
        raise FileNotFoundError(f"toolchain manifest does not exist: {manifest_path}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(manifest, dict) or manifest.get("schema") != TOOLCHAIN_SCHEMA:
        raise ValueError(f"invalid toolchain manifest: {manifest_path}")
    entries, current_digest = _tree_inventory(root)
    # The manifest itself was written after the recorded inventory.
    without_manifest = [item for item in entries if item["path"] != MANIFEST_NAME]
    current_digest = hashlib.sha256(
        json.dumps(
            without_manifest,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    replacements = {}
    for relative, expected in manifest.get("replacements", {}).items():
        installed = root / relative
        actual = file_sha256(installed) if installed.is_file() else None
        replacements[relative] = {
            "expected_sha256": expected["installed_sha256"],
            "actual_sha256": actual,
            "pass": actual == expected["installed_sha256"],
        }
    integrity = current_digest == manifest["installed_inventory_sha256"] and all(
        item["pass"] for item in replacements.values()
    )
    gates = dict(manifest["gates"])
    gates["real_copy"] = integrity
    return {
        "schema": TOOLCHAIN_SCHEMA,
        "directory": str(root),
        "manifest_sha256": file_sha256(manifest_path),
        "integrity": integrity,
        "gates": gates,
        "claim": "ready" if all(gates.values()) else "uncalibrated",
        "replacements": replacements,
        "next_missing_gates": [name for name, passed in gates.items() if not passed],
    }


def toolchain_environment(
    path: str | Path, *, require_ready: bool = False
) -> dict[str, str]:
    """Return the path-sensitive driver environment for one verified copy."""

    report = toolchain_status(path)
    if not report["integrity"]:
        raise ValueError("toolchain integrity failed")
    if require_ready and report["claim"] != "ready":
        missing = ", ".join(report["next_missing_gates"])
        raise ValueError(f"toolchain is not calibrated; missing gates: {missing}")
    return {"USR_LIB": report["directory"]}
