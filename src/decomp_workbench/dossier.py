"""Append-only, machine-queryable records of tested and falsified hypotheses."""

from __future__ import annotations

import hashlib
import json
import os
import time
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from .evidence import exclusive_file_lock

DOSSIER_ENTRY_SCHEMA = "decomp-workbench-dossier-entry-v1"
DOSSIER_REPORT_SCHEMA = "decomp-workbench-dossier-v1"
RESULTS = frozenset({"falsified", "supported", "inconclusive"})


def _line(value: str, *, field: str, limit: int) -> str:
    normalized = " ".join(value.replace("\x00", "").splitlines()).strip()
    if not normalized or len(normalized) > limit:
        raise ValueError(f"{field} must be one non-empty line up to {limit} characters")
    return normalized


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def _validated_body(value: Mapping[str, Any], *, where: str) -> dict[str, Any]:
    result = value.get("result")
    if result not in RESULTS:
        raise ValueError(
            f"{where}.result must be falsified, supported, or inconclusive"
        )
    do_not_repeat = value.get("do_not_repeat")
    if type(do_not_repeat) is not bool:
        raise ValueError(f"{where}.do_not_repeat must be a boolean")
    evidence = value.get("evidence")
    if not isinstance(evidence, Sequence) or isinstance(evidence, str | bytes):
        raise ValueError(f"{where}.evidence must be a list of strings")
    if any(not isinstance(item, str) for item in evidence):
        raise ValueError(f"{where}.evidence must contain only strings")
    fields = {
        "function": (160, value.get("function")),
        "hypothesis": (500, value.get("hypothesis")),
        "lever": (240, value.get("lever")),
        "outcome": (500, value.get("outcome")),
    }
    normalized: dict[str, Any] = {}
    for field, (limit, raw) in fields.items():
        if not isinstance(raw, str):
            raise ValueError(f"{where}.{field} must be a string")
        clean = _line(raw, field=f"{where}.{field}", limit=limit)
        if clean != raw:
            raise ValueError(f"{where}.{field} is not canonically normalized")
        normalized[field] = clean
    clean_evidence = [
        _line(item, field=f"{where}.evidence[{index}]", limit=500)
        for index, item in enumerate(evidence)
    ]
    if clean_evidence != list(evidence):
        raise ValueError(f"{where}.evidence is not canonically normalized")
    return {
        "function": normalized["function"],
        "hypothesis": normalized["hypothesis"],
        "lever": normalized["lever"],
        "result": result,
        "outcome": normalized["outcome"],
        "do_not_repeat": do_not_repeat,
        "evidence": clean_evidence,
    }


def append_entry(
    path: str | Path,
    *,
    function: str,
    hypothesis: str,
    lever: str,
    result: str,
    outcome: str,
    do_not_repeat: bool,
    evidence: Sequence[str] = (),
) -> dict[str, Any]:
    """Append one canonical record with an ID independent of wall-clock time."""

    body = _validated_body(
        {
            "function": function,
            "hypothesis": hypothesis,
            "lever": lever,
            "result": result,
            "outcome": outcome,
            "do_not_repeat": do_not_repeat,
            "evidence": list(evidence),
        },
        where="entry",
    )
    identifier = hashlib.sha256(_canonical(body)).hexdigest()[:24]
    entry = {
        "schema": DOSSIER_ENTRY_SCHEMA,
        "id": identifier,
        "recorded_at_unix": time.time(),
        **body,
    }
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    lock = destination.with_name(f".{destination.name}.lock")
    with exclusive_file_lock(lock):
        existing, _ = read_dossier(destination)
        if any(item["id"] == identifier for item in existing):
            raise ValueError(f"dossier already contains entry {identifier}")
        payload = (
            json.dumps(entry, sort_keys=True, separators=(",", ":")) + "\n"
        ).encode()
        descriptor = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644)
        try:
            offset = 0
            while offset < len(payload):
                written = os.write(descriptor, payload[offset:])
                if written <= 0:
                    raise OSError("dossier append made no progress")
                offset += written
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
    return entry


def read_dossier(path: str | Path) -> tuple[list[dict[str, Any]], list[str]]:
    """Read an append-only dossier, tolerating only a torn final line."""

    location = Path(path)
    if not location.exists():
        return [], []
    contents = location.read_text(encoding="utf-8")
    lines = contents.splitlines()
    final_line_is_torn = bool(lines) and not contents.endswith(("\n", "\r"))
    entries: list[dict[str, Any]] = []
    warnings: list[str] = []
    seen: set[str] = set()
    for index, line in enumerate(lines, 1):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError as error:
            if index == len(lines) and final_line_is_torn:
                warnings.append(f"ignored torn final dossier line {index}")
                break
            raise ValueError(f"malformed dossier line {index}: {error}") from None
        if (
            not isinstance(value, Mapping)
            or value.get("schema") != DOSSIER_ENTRY_SCHEMA
        ):
            raise ValueError(
                f"dossier line {index} is not a {DOSSIER_ENTRY_SCHEMA} record"
            )
        identifier = value.get("id")
        if (
            not isinstance(identifier, str)
            or len(identifier) != 24
            or any(char not in "0123456789abcdef" for char in identifier)
            or identifier in seen
        ):
            raise ValueError(f"dossier line {index} has a missing or duplicate id")
        recorded_at = value.get("recorded_at_unix")
        if (
            isinstance(recorded_at, bool)
            or not isinstance(recorded_at, int | float)
            or recorded_at < 0
        ):
            raise ValueError(f"dossier line {index} has an invalid recorded_at_unix")
        body = _validated_body(value, where=f"dossier line {index}")
        expected = hashlib.sha256(_canonical(body)).hexdigest()[:24]
        if identifier != expected:
            raise ValueError(
                f"dossier line {index} content does not match id {identifier}"
            )
        seen.add(identifier)
        entries.append(dict(value))
    return entries, warnings


def dossier_report(
    path: str | Path, *, function: str | None = None, result: str | None = None
) -> dict[str, Any]:
    entries, warnings = read_dossier(path)
    selected = [
        item
        for item in entries
        if (function is None or item.get("function") == function)
        and (result is None or item.get("result") == result)
    ]
    return {
        "schema": DOSSIER_REPORT_SCHEMA,
        "path": str(Path(path)),
        "entries": selected,
        "entry_count": len(selected),
        "do_not_repeat": sum(bool(item.get("do_not_repeat")) for item in selected),
        "warnings": warnings,
    }


__all__ = [
    "DOSSIER_ENTRY_SCHEMA",
    "DOSSIER_REPORT_SCHEMA",
    "RESULTS",
    "append_entry",
    "dossier_report",
    "read_dossier",
]
