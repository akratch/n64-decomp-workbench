"""Section-scoped object fidelity gates for compiler instrumentation and replay."""

from __future__ import annotations

import hashlib
import re
import subprocess
from pathlib import Path
from typing import Any

from .campaign import executable_identity, file_sha256
from .objdump import discover_objdump

FIDELITY_SCHEMA = "decomp-workbench-object-fidelity-v1"
DEFAULT_SECTIONS = (".text", ".rodata", ".data")
HEX_DUMP_ADDRESS_RE = re.compile(r"^\s*[0-9a-fA-F]+\s+")
HEX_DUMP_TOKEN_RE = re.compile(r"[0-9a-fA-F]{2,8}(?=\s|$)")


def _run(executable: str, arguments: list[str], *, timeout: float) -> str:
    process = subprocess.run(
        [executable, *arguments],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
    )
    if process.returncode:
        diagnostic = process.stderr.strip() or process.stdout.strip()
        # An absent optional section is stable evidence, not a tool failure.
        if "section" in diagnostic and "not found" in diagnostic:
            return ""
        raise RuntimeError(
            f"objdump {' '.join(arguments)} failed with exit "
            f"{process.returncode}: {diagnostic}"
        )
    return process.stdout


def _section_bytes(text: str) -> bytes:
    chunks: list[str] = []
    for line in text.splitlines():
        address = HEX_DUMP_ADDRESS_RE.match(line)
        if address is None:
            continue
        position = address.end()
        for _ in range(4):
            token = HEX_DUMP_TOKEN_RE.match(line, position)
            if token is None or len(token.group()) % 2:
                break
            chunks.append(token.group())
            position = token.end()
            whitespace = re.match(r"\s+", line[position:])
            if whitespace is None:
                break
            # GNU objdump separates the data field from its printable ASCII
            # column with at least two spaces. Stop before an ASCII word that
            # happens to consist entirely of hexadecimal characters.
            if len(whitespace.group()) >= 2:
                break
            position += len(whitespace.group())
    return bytes.fromhex("".join(chunks)) if chunks else b""


def _canonical_table(text: str) -> bytes:
    lines = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.endswith("file format elf32-bigmips"):
            continue
        if stripped.startswith(("SYMBOL TABLE:", "RELOCATION RECORDS FOR")):
            lines.append(stripped)
            continue
        # Remove the input filename/header while retaining every table row.
        if ":" in stripped and not re.match(r"^[0-9a-fA-F]", stripped):
            continue
        lines.append(re.sub(r"\s+", " ", stripped))
    return ("\n".join(lines) + "\n").encode("utf-8")


def object_fidelity_fingerprint(
    path: str | Path,
    *,
    objdump: str | None = None,
    sections: tuple[str, ...] = DEFAULT_SECTIONS,
    timeout: float = 10.0,
) -> dict[str, Any]:
    """Hash meaningful object sections while isolating unstable debug metadata."""

    object_path = Path(path).expanduser().resolve()
    if not object_path.is_file():
        raise FileNotFoundError(f"object does not exist: {object_path}")
    executable = discover_objdump(objdump)
    section_rows = {}
    for section in sections:
        content = _section_bytes(
            _run(executable, ["-s", "-j", section, str(object_path)], timeout=timeout)
        )
        section_rows[section] = {
            "present": bool(content),
            "bytes": len(content),
            "sha256": hashlib.sha256(content).hexdigest(),
        }
    relocations = _canonical_table(
        _run(executable, ["-r", str(object_path)], timeout=timeout)
    )
    symbols = _canonical_table(
        _run(executable, ["-t", str(object_path)], timeout=timeout)
    )
    return {
        "object": str(object_path),
        "file_sha256": file_sha256(object_path),
        "objdump": executable_identity([executable]),
        "sections": section_rows,
        "relocations_sha256": hashlib.sha256(relocations).hexdigest(),
        "symbols_sha256": hashlib.sha256(symbols).hexdigest(),
    }


def compare_object_fidelity(
    stock: str | Path,
    instrumented: str | Path,
    *,
    objdump: str | None = None,
    sections: tuple[str, ...] = DEFAULT_SECTIONS,
    timeout: float = 10.0,
) -> dict[str, Any]:
    """Compare the exact sections instrumentation is allowed to preserve."""

    expected = object_fidelity_fingerprint(
        stock,
        objdump=objdump,
        sections=sections,
        timeout=timeout,
    )
    actual = object_fidelity_fingerprint(
        instrumented,
        objdump=objdump,
        sections=sections,
        timeout=timeout,
    )
    gates = {
        section: expected["sections"][section] == actual["sections"][section]
        for section in sections
    }
    gates["relocations"] = (
        expected["relocations_sha256"] == actual["relocations_sha256"]
    )
    gates["symbols"] = expected["symbols_sha256"] == actual["symbols_sha256"]
    return {
        "schema": FIDELITY_SCHEMA,
        "pass": all(gates.values()),
        "gates": gates,
        "stock": expected,
        "instrumented": actual,
        "file_identical": expected["file_sha256"] == actual["file_sha256"],
        "proof": (
            "Section-scoped fidelity. Whole-file differences may remain in "
            "unstable debug metadata and are reported separately."
        ),
    }
