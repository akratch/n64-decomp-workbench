"""Fresh, auditable completion receipts for a measured campaign winner."""

from __future__ import annotations

import html
import json
import shlex
import tempfile
import time
from pathlib import Path
from typing import Any

from .artifacts import DEFAULT_STREAM_LIMIT, capture_streams
from .campaign import (
    CompilerTimeoutError,
    file_sha256,
    run_campaign,
    run_compiler,
)
from .campaign_state import build_status, resolve_manifest, validate_resume
from .collateral import compare_object_collateral
from .experiment_signals import required_signals_pass
from .experiments import load_experiment
from .handoff_audit import audit_handoff

FINISH_SCHEMA = "decomp-workbench-campaign-finish-v1"


def _gate(status: str, reason: str, evidence: Any = None) -> dict[str, Any]:
    return {"status": status, "reason": reason, "evidence": evidence}


def _function_exact(comparison: Any) -> bool:
    return bool(comparison is not None and comparison.exact)


def _scratch_accepted(comparison: Any) -> bool:
    return bool(
        comparison is not None
        and comparison.exact
        and comparison.raw_word_mismatches == 0
        and comparison.relocation_target_mismatches == 0
    )


def _selected(
    manifest: dict[str, Any], status: dict[str, Any], selection: str
) -> tuple[dict[str, Any], dict[str, Any], Path, Path]:
    selected_key = "best_temp_prefix" if selection == "temp-prefix" else "best"
    selected = status.get(selected_key)
    if not isinstance(selected, dict):
        raise ValueError("campaign has no successful candidate to finish")
    cache_key = selected.get("cache_key")
    source_record = next(
        (
            item
            for item in manifest.get("sources", [])
            if isinstance(item, dict) and item.get("cache_key") == cache_key
        ),
        None,
    )
    if not isinstance(source_record, dict):
        raise ValueError("selected ledger record is absent from the campaign manifest")
    source = Path(str(source_record["path"]))
    cache_object = Path(str(manifest["cache_directory"])) / f"{cache_key}.o"
    if not cache_object.is_file():
        raise FileNotFoundError(f"selected campaign object is absent: {cache_object}")
    actual_source = file_sha256(source)
    if actual_source != source_record.get("sha256"):
        raise ValueError("selected source hash changed; refusing finish")
    if selected.get("source_sha256") not in {None, actual_source}:
        raise ValueError("selected ledger source hash disagrees with the manifest")
    actual_object = file_sha256(cache_object)
    if selected.get("object_sha256") not in {None, actual_object}:
        raise ValueError("selected cached object hash changed; refusing finish")
    return selected, source_record, source, cache_object


def _write_report(path: Path, report: dict[str, Any], *, format: str) -> None:
    if path.exists():
        raise FileExistsError(f"refusing to overwrite campaign finish receipt: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    if format == "json":
        content = json.dumps(report, indent=2, sort_keys=True) + "\n"
    else:
        gates = "\n".join(
            "<tr>"
            f"<th>{html.escape(name.replace('_', ' '))}</th>"
            f"<td>{html.escape(str(gate['status']))}</td>"
            f"<td>{html.escape(str(gate['reason']))}</td>"
            "</tr>"
            for name, gate in report["gates"].items()
        )
        serialized = html.escape(json.dumps(report, indent=2, sort_keys=True))
        content = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>decomp-workbench campaign finish</title>
<style>:root{{color-scheme:light dark;font-family:ui-sans-serif,system-ui,sans-serif}}
body{{max-width:72rem;margin:2rem auto;padding:0 1rem;line-height:1.5}}
table{{border-collapse:collapse;width:100%}}
th,td{{padding:.5rem;border-bottom:1px solid #8886;text-align:left}}
pre{{overflow:auto;padding:1rem;background:#8881}}</style></head><body>
<h1>Campaign finish: {html.escape(str(report["status"]))}</h1>
<p>Source <code>{html.escape(str(report["winner"]["source"]))}</code></p>
<table><thead><tr><th>Gate</th><th>Status</th><th>Reason</th></tr></thead>
<tbody>{gates}</tbody></table>
<details><summary>Machine-readable receipt</summary><pre>{serialized}</pre></details>
</body></html>"""
    with path.open("x", encoding="utf-8") as destination:
        destination.write(content)


def finish_campaign(
    campaign: str | Path,
    *,
    selection: str = "score",
    output: str | Path | None = None,
    format: str = "json",
    scratch_context: str | Path | None = None,
    scratch_compile_command: str | None = None,
    collateral_reference: str | Path | None = None,
    handoff: str | Path | None = None,
    project_command: str | None = None,
    project_timeout: float = 120.0,
    stream_limit: int = DEFAULT_STREAM_LIMIT,
) -> tuple[dict[str, Any], Path]:
    """Freshly rebuild one immutable winner and evaluate independent gates."""

    if selection not in {"score", "temp-prefix"}:
        raise ValueError("finish selection must be score or temp-prefix")
    if format not in {"json", "html"}:
        raise ValueError("finish format must be json or html")
    manifest_path = resolve_manifest(campaign)
    manifest = validate_resume(manifest_path)
    status = build_status(manifest_path)
    selected, source_record, source, cache_object = _selected(
        manifest, status, selection
    )
    report_path = (
        Path(output).expanduser().resolve()
        if output is not None
        else manifest_path.parent / f"finish.{format}"
    )
    if report_path.exists():
        raise FileExistsError(
            f"refusing to overwrite campaign finish receipt: {report_path}"
        )

    inputs = manifest["identity_inputs"]
    compile_info = inputs["compile"]
    experiment_definition = manifest.get("experiment")
    experiment = None
    if isinstance(experiment_definition, dict) and isinstance(
        experiment_definition.get("path"), str
    ):
        experiment = load_experiment(experiment_definition["path"])
    gates: dict[str, dict[str, Any]] = {
        "fresh_function": _gate("UNKNOWN", "fresh rebuild did not run"),
        "required_signals": _gate("UNKNOWN", "fresh rebuild did not run"),
        "scratch_context": _gate("NOT RUN", "no scratch context supplied"),
        "translation_unit_collateral": _gate(
            "NOT RUN", "no collateral reference supplied"
        ),
        "handoff": _gate("NOT RUN", "no handoff directory supplied"),
        "project_verification": _gate("NOT RUN", "no project command supplied"),
    }
    fresh_result = None
    with tempfile.TemporaryDirectory(prefix="decomp-workbench-finish-") as temporary:
        root = Path(temporary)
        fresh_results, _ = run_campaign(
            [source],
            target=inputs["target"]["path"],
            template=compile_info["template"],
            cache_dir=root / "fresh-cache",
            jobs=1,
            objdump=inputs["objdump"]["requested"],
            symbol=inputs.get("symbol"),
            section=inputs["section"],
            environment=compile_info["environment"],
            compile_cwd=compile_info["working_directory"],
            keep_objects=root / "fresh-object",
            stop_on_exact=False,
            timeout=manifest["execution"]["timeout_seconds"],
            stream_limit=stream_limit,
            artifact_dir=report_path.parent / f"{report_path.stem}-artifacts",
            signal_specs=experiment.signals if experiment else (),
            compilation_envelope=compile_info.get("envelope", {}),
        )
        fresh_result = fresh_results[0]
        fresh_comparison = fresh_result.comparison
        if fresh_comparison is not None and _function_exact(fresh_comparison):
            gates["fresh_function"] = _gate(
                "PASS",
                "fresh no-cache rebuild passes built-in function exactness",
                fresh_comparison.as_dict(),
            )
        else:
            gates["fresh_function"] = _gate(
                "FAIL",
                "fresh no-cache rebuild is not function exact",
                fresh_result.as_dict(),
            )
        gates["required_signals"] = _gate(
            "PASS" if required_signals_pass(fresh_result.signals) else "FAIL",
            (
                "all required signals passed on the fresh object"
                if required_signals_pass(fresh_result.signals)
                else "one or more required signals failed or were unknown"
            ),
            fresh_result.signals,
        )
        fresh_object = (
            Path(fresh_result.object_path) if fresh_result.object_path else None
        )

        if scratch_context is not None:
            try:
                context_path = Path(scratch_context).expanduser().resolve()
                if not context_path.is_file():
                    raise FileNotFoundError(
                        f"scratch context does not exist: {context_path}"
                    )
                composed = root / source.name
                context = context_path.read_bytes()
                composed.write_bytes(
                    context
                    + (b"" if context.endswith(b"\n") else b"\n")
                    + f'#line 1 "{source.name}"\n'.encode()
                    + source.read_bytes()
                )
                scratch_results, _ = run_campaign(
                    [composed],
                    target=inputs["target"]["path"],
                    template=scratch_compile_command or compile_info["template"],
                    cache_dir=root / "scratch-cache",
                    jobs=1,
                    objdump=inputs["objdump"]["requested"],
                    symbol=inputs.get("symbol"),
                    section=inputs["section"],
                    environment=compile_info["environment"],
                    compile_cwd=compile_info["working_directory"],
                    stop_on_exact=False,
                    timeout=manifest["execution"]["timeout_seconds"],
                    stream_limit=stream_limit,
                    compilation_envelope=compile_info.get("envelope", {}),
                )
                scratch_result = scratch_results[0]
                gates["scratch_context"] = _gate(
                    "PASS" if _scratch_accepted(scratch_result.comparison) else "FAIL",
                    (
                        "scratch-context rebuild is accepted"
                        if _scratch_accepted(scratch_result.comparison)
                        else "scratch-context rebuild differs; project truth "
                        "remains separate"
                    ),
                    scratch_result.as_dict(),
                )
            except (OSError, RuntimeError, ValueError) as error:
                gates["scratch_context"] = _gate("FAIL", str(error))

        if collateral_reference is not None:
            try:
                if fresh_object is None:
                    raise ValueError("fresh object is unavailable for collateral check")
                collateral = compare_object_collateral(
                    collateral_reference,
                    fresh_object,
                    symbol=inputs.get("symbol"),
                    section=inputs["section"],
                    objdump=inputs["objdump"]["requested"],
                )
                gates["translation_unit_collateral"] = _gate(
                    "FAIL" if collateral["collateral_detected"] else "PASS",
                    (
                        "translation-unit collateral was detected"
                        if collateral["collateral_detected"]
                        else "no scoped translation-unit collateral was detected"
                    ),
                    collateral,
                )
            except (OSError, RuntimeError, ValueError) as error:
                gates["translation_unit_collateral"] = _gate("FAIL", str(error))

        if handoff is not None:
            try:
                audit = audit_handoff(handoff)
                gates["handoff"] = _gate(
                    "PASS" if audit["ready"] else "FAIL",
                    "handoff is ready" if audit["ready"] else "handoff needs attention",
                    audit,
                )
            except (OSError, ValueError) as error:
                gates["handoff"] = _gate("FAIL", str(error))

        if project_command is not None:
            command = shlex.split(project_command)
            if not command:
                gates["project_verification"] = _gate(
                    "FAIL", "project command is empty"
                )
            else:
                started = time.monotonic()
                try:
                    process = run_compiler(
                        command,
                        environment=compile_info["environment"],
                        compile_cwd=Path(compile_info["working_directory"]),
                        timeout=project_timeout,
                    )
                    streams = capture_streams(
                        process.stdout,
                        process.stderr,
                        limit=stream_limit,
                        artifact_dir=report_path.parent
                        / f"{report_path.stem}-artifacts",
                        stem="project-verification",
                    )
                    evidence = {
                        "command": command,
                        "returncode": process.returncode,
                        "duration_seconds": time.monotonic() - started,
                        "stdout": streams.stdout,
                        "stderr": streams.stderr,
                        "stdout_bytes": streams.stdout_bytes,
                        "stderr_bytes": streams.stderr_bytes,
                        "stdout_truncated": streams.stdout_truncated,
                        "stderr_truncated": streams.stderr_truncated,
                        "artifacts": streams.artifacts,
                    }
                    gates["project_verification"] = _gate(
                        "PASS" if process.returncode == 0 else "FAIL",
                        (
                            "project command passed"
                            if process.returncode == 0
                            else f"project command exited {process.returncode}"
                        ),
                        evidence,
                    )
                except CompilerTimeoutError as error:
                    streams = capture_streams(
                        error.stdout,
                        error.stderr,
                        limit=stream_limit,
                        artifact_dir=report_path.parent
                        / f"{report_path.stem}-artifacts",
                        stem="project-verification-timeout",
                    )
                    gates["project_verification"] = _gate(
                        "FAIL",
                        str(error),
                        {
                            "command": command,
                            "returncode": 124,
                            "duration_seconds": time.monotonic() - started,
                            "stdout": streams.stdout,
                            "stderr": streams.stderr,
                            "stdout_bytes": streams.stdout_bytes,
                            "stderr_bytes": streams.stderr_bytes,
                            "stdout_truncated": streams.stdout_truncated,
                            "stderr_truncated": streams.stderr_truncated,
                            "artifacts": streams.artifacts,
                        },
                    )
                except OSError as error:
                    gates["project_verification"] = _gate("FAIL", str(error))

    evaluated = [gate for gate in gates.values() if gate["status"] != "NOT RUN"]
    ready = bool(evaluated) and all(gate["status"] == "PASS" for gate in evaluated)
    report = {
        "schema": FINISH_SCHEMA,
        "generated_at_unix": time.time(),
        "status": "PASS" if ready else "FAIL",
        "ready": ready,
        "campaign_identity": manifest["identity"],
        "campaign_manifest": str(manifest_path),
        "selection": selection,
        "winner": {
            "source": str(source),
            "source_sha256": source_record["sha256"],
            "cache_key": selected["cache_key"],
            "recorded_object": str(cache_object),
            "recorded_object_sha256": file_sha256(cache_object),
            "recorded_at_unix": selected.get("recorded_at_unix"),
            "fresh_object_sha256": (
                fresh_result.object_sha256 if fresh_result is not None else None
            ),
            "target_sha256": inputs["target"]["sha256"],
        },
        "gates": gates,
        "proof": (
            "Each gate is independent. NOT RUN never means PASS; function "
            "exactness does not imply scratch, collateral, handoff, or project truth."
        ),
    }
    _write_report(report_path, report, format=format)
    return report, report_path
