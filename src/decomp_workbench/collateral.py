"""Translation-unit collateral beyond one selected function."""

from __future__ import annotations

import fnmatch
import hashlib
import re
from pathlib import Path
from typing import Any

from .compare import compare_objects
from .fidelity import _canonical_table, _run, _section_bytes
from .objdump import discover_objdump

COLLATERAL_SCHEMA = "decomp-workbench-object-collateral-v1"
DEFAULT_IGNORES = (".debug*", ".mdebug*", ".comment", ".note*")
SECTION_RE = re.compile(
    r"^\s*\d+\s+(?P<name>\S+)\s+(?P<size>[0-9a-fA-F]+)\s+"
    r"[0-9a-fA-F]+\s+[0-9a-fA-F]+\s+[0-9a-fA-F]+\s+"
    r"2\*\*(?P<alignment>\d+)\s*$"
)


def _ignored(name: str, patterns: tuple[str, ...]) -> bool:
    return any(fnmatch.fnmatchcase(name, pattern) for pattern in patterns)


def object_section_inventory(
    path: str | Path,
    *,
    objdump: str | None = None,
    ignore: tuple[str, ...] = DEFAULT_IGNORES,
    timeout: float = 10.0,
) -> dict[str, dict[str, Any]]:
    """Return section sizes, flags, and content hashes, including zero-fill."""

    object_path = Path(path).expanduser().resolve()
    if not object_path.is_file():
        raise FileNotFoundError(f"object does not exist: {object_path}")
    executable = discover_objdump(objdump)
    lines = _run(executable, ["-h", str(object_path)], timeout=timeout).splitlines()
    result: dict[str, dict[str, Any]] = {}
    for index, line in enumerate(lines):
        match = SECTION_RE.match(line)
        if match is None:
            continue
        name = match.group("name")
        if _ignored(name, ignore):
            continue
        if name in result:
            raise ValueError(
                f"object has duplicate in-scope section name {name!r}: {object_path}"
            )
        flags = []
        if index + 1 < len(lines) and not SECTION_RE.match(lines[index + 1]):
            flags = [item.strip() for item in lines[index + 1].split(",")]
            flags = [item for item in flags if item]
        has_contents = "CONTENTS" in flags
        content = (
            _section_bytes(
                _run(
                    executable,
                    ["-s", "-j", name, str(object_path)],
                    timeout=timeout,
                )
            )
            if has_contents
            else b""
        )
        size = int(match.group("size"), 16)
        if has_contents and len(content) != size:
            raise ValueError(
                f"objdump returned {len(content)} of {size} byte(s) for "
                f"section {name!r}: {object_path}"
            )
        result[name] = {
            "size": size,
            "alignment": 1 << int(match.group("alignment")),
            "flags": flags,
            "has_contents": has_contents,
            "content_sha256": hashlib.sha256(content).hexdigest()
            if has_contents
            else None,
        }
    return result


def _table_hash(executable: str, path: Path, option: str, *, timeout: float) -> str:
    data = _canonical_table(_run(executable, [option, str(path)], timeout=timeout))
    return hashlib.sha256(data).hexdigest()


def compare_object_collateral(
    reference: str | Path,
    candidate: str | Path,
    *,
    symbol: str | None = None,
    section: str = ".text",
    objdump: str | None = None,
    ignore: tuple[str, ...] = DEFAULT_IGNORES,
    timeout: float = 10.0,
) -> dict[str, Any]:
    """Report full-object changes that a function-only comparison cannot see."""

    reference_path = Path(reference).expanduser().resolve()
    candidate_path = Path(candidate).expanduser().resolve()
    executable = discover_objdump(objdump)
    before = object_section_inventory(
        reference_path, objdump=executable, ignore=ignore, timeout=timeout
    )
    after = object_section_inventory(
        candidate_path, objdump=executable, ignore=ignore, timeout=timeout
    )
    if not before or not after:
        raise ValueError(
            "objdump returned no in-scope sections; verify --objdump and "
            "--ignore-section before treating this as a collateral result"
        )
    section_changes = []
    for name in sorted(set(before) | set(after)):
        expected = before.get(name)
        actual = after.get(name)
        changed = []
        if expected is None or actual is None:
            changed.append("presence")
        else:
            for field in ("size", "alignment", "flags", "content_sha256"):
                if expected[field] != actual[field]:
                    changed.append(field)
        if changed:
            section_changes.append(
                {
                    "section": name,
                    "changed": changed,
                    "size_delta": (actual["size"] if actual else 0)
                    - (expected["size"] if expected else 0),
                    "reference": expected,
                    "candidate": actual,
                }
            )
    relocation_identical = _table_hash(
        executable, reference_path, "-r", timeout=timeout
    ) == _table_hash(executable, candidate_path, "-r", timeout=timeout)
    symbol_table_identical = _table_hash(
        executable, reference_path, "-t", timeout=timeout
    ) == _table_hash(executable, candidate_path, "-t", timeout=timeout)
    function = None
    function_exact = None
    if symbol is not None:
        comparison = compare_objects(
            reference_path,
            candidate_path,
            objdump=executable,
            symbol=symbol,
            section=section,
        )
        function = comparison.as_dict()
        function_exact = (
            comparison.raw_word_mismatches == 0
            and comparison.relocation_target_mismatches == 0
            and comparison.exact
        )
    collateral_detected = bool(
        section_changes or not relocation_identical or not symbol_table_identical
    )
    classification = (
        "none"
        if not collateral_detected
        else "outside-selected-function"
        if function_exact
        else "translation-unit-difference"
    )
    return {
        "schema": COLLATERAL_SCHEMA,
        "reference": str(reference_path),
        "candidate": str(candidate_path),
        "selected_symbol": symbol,
        "selected_function_exact": function_exact,
        "selected_function": function,
        "classification": classification,
        "collateral_detected": collateral_detected,
        "ignored_sections": list(ignore),
        "section_changes": section_changes,
        "section_change_count": len(section_changes),
        "relocations_identical": relocation_identical,
        "symbol_table_identical": symbol_table_identical,
        "proof": (
            "Section sizes include zero-fill sections such as .bss; content, "
            "relocation, and symbol-table checks are translation-unit evidence. "
            "Selected-function exactness remains a separate gate and does not "
            "establish whole-object or whole-ROM identity."
        ),
        "next_gate": (
            "Remove or explain the listed translation-unit changes, then run "
            "the normal project link/ROM verification."
            if collateral_detected
            else "Run the normal project link/ROM verification."
        ),
    }
