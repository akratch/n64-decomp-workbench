"""Redistributable compiler microcases and cross-revision lineage reports."""

from __future__ import annotations

import collections
import hashlib
import json
import re
import tempfile
import time
from pathlib import Path
from typing import Any

from .artifacts import DEFAULT_STREAM_LIMIT, capture_streams
from .campaign import (
    CompilerTimeoutError,
    executable_identity,
    file_sha256,
    render_compile_command,
    run_compiler,
)
from .compare import compare_objects, frame_size, normalize_instruction
from .model import Instruction
from .objdump import discover_objdump, dump_object
from .view import destination_register

FINGERPRINT_SCHEMA = "decomp-workbench-toolchain-fingerprint-v1"
LINEAGE_SCHEMA = "decomp-workbench-cross-rom-lineage-v1"
MICROCASES = (
    ("control-flow", "control_flow.c", "dkwb_fp_control_flow"),
    ("stack-home", "stack_home.c", "dkwb_fp_stack_home"),
    ("schedule", "schedule.c", "dkwb_fp_schedule"),
    ("allocation", "allocation.c", "dkwb_fp_allocation"),
    ("dense-switch-4", "dense_switch_4.c", "dkwb_fp_dense_switch_4"),
    ("dense-switch-5", "dense_switch_5.c", "dkwb_fp_dense_switch_5"),
)


def instruction_fingerprint(instructions: list[Instruction]) -> dict[str, Any]:
    """Describe lowering, scheduling, frame, and register-allocation idioms."""

    opcodes = [item.opcode for item in instructions]
    normalized = [normalize_instruction(item.assembly) for item in instructions]
    destination_sequence = [
        register
        for item in instructions
        if (register := destination_register(item.assembly)) is not None
    ]
    branch_ops = [
        item.opcode
        for item in instructions
        if item.opcode.startswith("b") or item.opcode in {"j", "jr", "jal", "jalr"}
    ]
    calls = sum(item.opcode in {"jal", "jalr"} for item in instructions)
    computed_jumps = []
    for item in instructions:
        if item.opcode != "jr":
            continue
        parts = item.assembly.split(maxsplit=1)
        register = (
            parts[1].split(",", 1)[0].strip().lstrip("$") if len(parts) > 1 else ""
        )
        if register not in {"ra", "31"}:
            computed_jumps.append(item.assembly)
    payload = "".join(item.word for item in instructions).encode("ascii")
    normalized_payload = "\n".join(normalized).encode("utf-8")
    schedule_ngrams = collections.Counter(
        "/".join(opcodes[index : index + 3])
        for index in range(max(0, len(opcodes) - 2))
    )
    return {
        "instructions": len(instructions),
        "frame_size": frame_size("\n".join(item.assembly for item in instructions)),
        "opcode_histogram": dict(sorted(collections.Counter(opcodes).items())),
        "branch_skeleton": branch_ops,
        "call_count": calls,
        "computed_jump": bool(computed_jumps),
        "computed_jumps": computed_jumps,
        "float_loads": sum(item.opcode in {"lwc1", "ldc1"} for item in instructions),
        "float_stores": sum(item.opcode in {"swc1", "sdc1"} for item in instructions),
        "destination_registers": destination_sequence,
        "schedule_ngrams": dict(sorted(schedule_ngrams.items())),
        "word_sha256": hashlib.sha256(payload).hexdigest(),
        "normalized_sha256": hashlib.sha256(normalized_payload).hexdigest(),
    }


def object_fingerprint(
    path: str | Path,
    *,
    objdump: str | None,
    symbol: str | None,
    section: str = ".text",
) -> dict[str, Any]:
    """Fingerprint one object symbol with reproducibility hashes."""

    object_path = Path(path).expanduser().resolve()
    _, instructions = dump_object(
        object_path,
        objdump=objdump,
        symbol=symbol,
        section=section,
    )
    return {
        "object": str(object_path),
        "object_sha256": file_sha256(object_path),
        "symbol": symbol,
        "features": instruction_fingerprint(instructions),
    }


def run_toolchain_fingerprint(
    template: str,
    *,
    compile_cwd: str | Path,
    environment: dict[str, str],
    objdump: str | None,
    timeout: float,
    stream_limit: int = DEFAULT_STREAM_LIMIT,
    artifact_dir: str | Path | None = None,
) -> dict[str, Any]:
    """Compile bundled microcases and combine their feature signatures."""

    cwd = Path(compile_cwd).expanduser().resolve()
    if not cwd.is_dir():
        raise NotADirectoryError(f"compiler working directory does not exist: {cwd}")
    objdump_path = discover_objdump(objdump)
    cases_root = Path(__file__).with_name("fingerprints")
    cases = []
    compiler_identity: dict[str, Any] | None = None
    with tempfile.TemporaryDirectory(
        prefix="decomp-workbench-fingerprint-"
    ) as temporary:
        output_root = Path(temporary)
        for name, filename, symbol in MICROCASES:
            source = cases_root / filename
            if not source.is_file():
                raise FileNotFoundError(f"bundled fingerprint case missing: {source}")
            output = output_root / f"{name}.o"
            command = render_compile_command(template, source, output)
            compiler_identity = executable_identity(command, cwd=cwd)
            started = time.monotonic()
            try:
                process = run_compiler(
                    command,
                    environment=environment,
                    compile_cwd=cwd,
                    timeout=timeout,
                )
            except CompilerTimeoutError as error:
                raise RuntimeError(f"fingerprint case {name} {error}") from error
            streams = capture_streams(
                process.stdout,
                process.stderr,
                limit=stream_limit,
                artifact_dir=artifact_dir,
                stem=f"fingerprint-{name}",
            )
            if process.returncode:
                raise RuntimeError(
                    f"fingerprint case {name} failed with exit "
                    f"{process.returncode}: "
                    f"{streams.stderr.strip() or streams.stdout.strip()}"
                )
            if not output.is_file():
                raise RuntimeError(f"fingerprint case {name} did not create its object")
            case = object_fingerprint(
                output,
                objdump=objdump_path,
                symbol=symbol,
            )
            case.update(
                {
                    "name": name,
                    "source_sha256": file_sha256(source),
                    "duration_seconds": time.monotonic() - started,
                    "stdout": streams.stdout,
                    "stderr": streams.stderr,
                    "stdout_truncated": streams.stdout_truncated,
                    "stderr_truncated": streams.stderr_truncated,
                    "artifacts": streams.artifacts,
                }
            )
            cases.append(case)
    identity_payload = {case["name"]: case["features"] for case in cases}
    suite_payload = {case["name"]: case["source_sha256"] for case in cases}
    suite = hashlib.sha256(
        json.dumps(suite_payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    fingerprint = hashlib.sha256(
        json.dumps(identity_payload, sort_keys=True, separators=(",", ":")).encode(
            "utf-8"
        )
    ).hexdigest()
    return {
        "schema": FINGERPRINT_SCHEMA,
        "suite": suite,
        "fingerprint": fingerprint,
        "compiler": compiler_identity,
        "objdump": executable_identity([objdump_path], cwd=cwd),
        "working_directory": str(cwd),
        "explicit_environment": environment,
        "cases": cases,
        "proof": (
            "Redistributable behavioral fingerprint, not a claim of compiler "
            "version identity unless compared with a separately established record."
        ),
    }


def compare_fingerprint_reports(
    target: dict[str, Any],
    candidate: dict[str, Any],
) -> dict[str, Any]:
    """Compare two previously captured toolchain fingerprints."""

    target_cases = {item["name"]: item for item in target.get("cases", [])}
    candidate_cases = {item["name"]: item for item in candidate.get("cases", [])}
    target_suite = target.get("suite") or _report_suite(target_cases)
    candidate_suite = candidate.get("suite") or _report_suite(candidate_cases)
    compatible = target_suite is not None and target_suite == candidate_suite
    differences = []
    for name in sorted(set(target_cases) | set(candidate_cases)):
        expected = target_cases.get(name)
        actual = candidate_cases.get(name)
        if expected == actual:
            continue
        expected_features = expected.get("features", {}) if expected else {}
        actual_features = actual.get("features", {}) if actual else {}
        changed = sorted(
            key
            for key in set(expected_features) | set(actual_features)
            if expected_features.get(key) != actual_features.get(key)
        )
        differences.append({"case": name, "changed_features": changed})
    return {
        "schema": "decomp-workbench-toolchain-fingerprint-diff-v1",
        "compatible": compatible,
        "identical": compatible
        and target.get("fingerprint") == candidate.get("fingerprint"),
        "target_suite": target_suite,
        "candidate_suite": candidate_suite,
        "target_fingerprint": target.get("fingerprint"),
        "candidate_fingerprint": candidate.get("fingerprint"),
        "differences": differences,
    }


def _report_suite(cases: dict[str, dict[str, Any]]) -> str | None:
    """Recover a suite identity from legacy reports that predate the field."""

    payload = {
        name: item.get("source_sha256")
        for name, item in cases.items()
        if isinstance(item.get("source_sha256"), str)
    }
    if len(payload) != len(cases) or not payload:
        return None
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def cross_rom_lineage(
    revisions: dict[str, Path],
    *,
    objdump: str | None,
    symbol: str,
    section: str = ".text",
    rom_hashes: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Compare equivalent symbols across revisions without reading ROM data."""

    if len(revisions) < 2:
        raise ValueError("lineage requires at least two label=object revisions")
    if len(revisions) > 16:
        raise ValueError("lineage accepts at most 16 revisions per report")
    supplied_rom_hashes = rom_hashes or {}
    unknown_hashes = sorted(set(supplied_rom_hashes) - set(revisions))
    if unknown_hashes:
        raise ValueError(
            "ROM hash label(s) have no matching revision: " + ", ".join(unknown_hashes)
        )
    invalid_hashes = sorted(
        label
        for label, digest in supplied_rom_hashes.items()
        if re.fullmatch(r"[0-9a-fA-F]{64}", digest) is None
    )
    if invalid_hashes:
        raise ValueError(
            "ROM hashes must be 64 hexadecimal characters: " + ", ".join(invalid_hashes)
        )
    normalized_rom_hashes = {
        label: digest.lower() for label, digest in supplied_rom_hashes.items()
    }
    items = {
        label: object_fingerprint(
            path,
            objdump=objdump,
            symbol=symbol,
            section=section,
        )
        for label, path in revisions.items()
    }
    pairs = []
    labels = sorted(revisions)
    for left_index, left in enumerate(labels):
        for right in labels[left_index + 1 :]:
            comparison = compare_objects(
                revisions[left],
                revisions[right],
                objdump=objdump,
                symbol=symbol,
                section=section,
            )
            pairs.append(
                {
                    "left": left,
                    "right": right,
                    "exact": comparison.exact,
                    "structural_exact": comparison.structural_exact,
                    "verdict": comparison.verdict,
                    "aligned_total": comparison.aligned_total,
                    "words": comparison.word_mismatches,
                }
            )
    normalized_groups: dict[str, list[str]] = collections.defaultdict(list)
    for label, item in items.items():
        normalized_groups[item["features"]["normalized_sha256"]].append(label)
    groups = [
        {"normalized_sha256": digest, "revisions": sorted(group)}
        for digest, group in normalized_groups.items()
    ]
    groups.sort(key=lambda item: (-len(item["revisions"]), item["normalized_sha256"]))
    return {
        "schema": LINEAGE_SCHEMA,
        "symbol": symbol,
        "revisions": {
            label: {
                **item,
                "rom_sha256": normalized_rom_hashes.get(label),
            }
            for label, item in items.items()
        },
        "pairs": pairs,
        "normalized_lineage_groups": groups,
        "anomalies": [
            group["revisions"][0] for group in groups if len(group["revisions"]) == 1
        ],
        "proof": (
            "Object-derived lineage evidence. ROM hashes are caller-supplied "
            "identities; this command never reads or redistributes ROM data."
        ),
    }
