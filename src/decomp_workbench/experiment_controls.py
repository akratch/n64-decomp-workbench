"""Serial control preflight for experiment-v2 campaigns."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .campaign import prepare_candidates, run_campaign
from .experiments import ControlSpec, ExperimentManifest
from .model import CompileResult
from .schema import METRICS_BY_KEY


def _metrics(result: CompileResult) -> dict[str, Any]:
    if result.comparison is None:
        return {}
    payload = result.comparison.as_dict()
    return {
        key: payload.get(key)
        for key in METRICS_BY_KEY
        if isinstance(payload.get(key), (str, int, float, bool))
        or payload.get(key) is None
    }


def _candidate_receipt(
    result: CompileResult, provenance: dict[str, object]
) -> dict[str, Any]:
    return {
        "source": provenance["source"],
        "source_sha256": provenance["source_sha256"],
        "cache_key": result.cache_key,
        "command": result.command,
        "compile_cwd": provenance["compile_cwd"],
        "environment": provenance["environment"],
        "compiler": provenance["compiler"],
        "objdump": provenance["objdump"],
        "target_sha256": provenance["target_sha256"],
        "compilation_envelope": provenance.get("compilation_envelope", {}),
        "returncode": result.returncode,
        "object_sha256": result.object_sha256,
        "metrics": _metrics(result),
        "signals": result.signals,
    }


def _signal_status(receipt: dict[str, Any], signal_id: str) -> Any:
    return next(
        (
            item.get("status")
            for item in receipt["signals"]
            if item.get("id") == signal_id
        ),
        None,
    )


def _absolute(
    control: ControlSpec, candidate: dict[str, Any]
) -> tuple[str, str, list[str]]:
    failures: list[str] = []
    unknown: list[str] = []
    expect = control.expect
    metrics = dict(expect.get("metrics", {}))
    metrics.update(
        {key: value for key, value in expect.items() if key in METRICS_BY_KEY}
    )
    if candidate["returncode"] != int(expect.get("returncode", 0)):
        failures.append("returncode")
    for key, wanted in metrics.items():
        if key not in candidate["metrics"] or candidate["metrics"][key] is None:
            unknown.append(f"metrics.{key}")
        elif candidate["metrics"][key] != wanted:
            failures.append(f"metrics.{key}")
    for signal_id, wanted in expect.get("signals", {}).items():
        observed = _signal_status(candidate, signal_id)
        if observed is None:
            unknown.append(f"signals.{signal_id}")
        elif observed != wanted:
            failures.append(f"signals.{signal_id}")
    if "object_sha256" in expect:
        if candidate["object_sha256"] is None:
            unknown.append("object_sha256")
        elif candidate["object_sha256"] != expect["object_sha256"]:
            failures.append("object_sha256")
    if unknown:
        return "UNKNOWN", "expected control evidence was unavailable", unknown
    if failures:
        return (
            "FAIL",
            "absolute control did not reproduce its expected receipt",
            failures,
        )
    return "PASS", "absolute control reproduced every expected value", []


def _path(receipt: dict[str, Any], name: str) -> Any:
    if name == "object_sha256":
        return receipt.get("object_sha256")
    prefix, separator, key = name.partition(".")
    if not separator:
        return None
    if prefix == "metrics":
        return receipt["metrics"].get(key)
    if prefix == "signals":
        return _signal_status(receipt, key)
    return None


def _differential(
    control: ControlSpec, left: dict[str, Any], right: dict[str, Any]
) -> tuple[str, str, list[str]]:
    names = control.expect.get("different")
    if not isinstance(names, list) or not names:
        return "UNKNOWN", "differential control has no requested evidence paths", []
    unchanged: list[str] = []
    unavailable: list[str] = []
    for name in names:
        left_value = _path(left, str(name))
        right_value = _path(right, str(name))
        if left_value is None or right_value is None:
            unavailable.append(str(name))
        elif left_value == right_value:
            unchanged.append(str(name))
    if unavailable:
        return "UNKNOWN", "differential evidence was unavailable", unavailable
    if unchanged:
        return (
            "FAIL",
            "requested force/environment differential did not fire",
            unchanged,
        )
    return "PASS", "every requested differential changed", []


def run_control_preflight(
    manifest: ExperimentManifest,
    *,
    target: str | Path,
    template: str,
    cache_dir: str | Path,
    objdump: str,
    symbol: str | None,
    section: str,
    environment: dict[str, str],
    compile_cwd: str | Path,
    timeout: float | None,
    stream_limit: int,
    artifact_dir: str | Path | None,
    compilation_envelope: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Compile all declared controls serially before ordinary candidates."""

    if not manifest.controls:
        return {"status": "NOT DECLARED", "passed": True, "receipts": []}
    ordered_sources: list[Path] = []
    for control in manifest.controls:
        for source in control.candidates:
            if source not in ordered_sources:
                ordered_sources.append(source)
    results, _ = run_campaign(
        ordered_sources,
        target=target,
        template=template,
        cache_dir=cache_dir,
        jobs=1,
        objdump=objdump,
        symbol=symbol,
        section=section,
        environment=environment,
        compile_cwd=compile_cwd,
        stop_on_exact=False,
        timeout=timeout,
        stream_limit=stream_limit,
        artifact_dir=artifact_dir,
        signal_specs=manifest.signals,
        compilation_envelope=compilation_envelope,
    )
    prepared, _ = prepare_candidates(
        ordered_sources,
        template=template,
        target=Path(target).expanduser().resolve(),
        symbol=symbol,
        environment=environment,
        compile_cwd=Path(compile_cwd).expanduser().resolve(),
        section=section,
        objdump=objdump,
        compilation_envelope=compilation_envelope,
    )
    provenance = {candidate.cache_key: candidate.provenance for candidate in prepared}
    by_source = {
        str(Path(source).expanduser().resolve()): _candidate_receipt(
            result, provenance[result.cache_key]
        )
        for source, result in (
            (
                next(
                    candidate.source
                    for candidate in prepared
                    if candidate.cache_key == item.cache_key
                ),
                item,
            )
            for item in results
        )
    }
    receipts: list[dict[str, Any]] = []
    for control in manifest.controls:
        candidates = [by_source[str(source)] for source in control.candidates]
        if control.kind == "absolute":
            status, reason, failed = _absolute(control, candidates[0])
        else:
            status, reason, failed = _differential(
                control, candidates[0], candidates[1]
            )
        receipts.append(
            {
                "id": control.id,
                "kind": control.kind,
                "required": control.required,
                "status": status,
                "reason": reason,
                "failed_evidence": failed,
                "candidates": candidates,
            }
        )
    passed = all(
        receipt["status"] == "PASS" for receipt in receipts if receipt["required"]
    )
    return {
        "status": "PASS" if passed else "FAIL",
        "passed": passed,
        "required": sum(1 for control in manifest.controls if control.required),
        "passed_required": sum(
            1
            for receipt in receipts
            if receipt["required"] and receipt["status"] == "PASS"
        ),
        "receipts": receipts,
    }
