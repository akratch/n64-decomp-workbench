"""Objdump discovery, invocation, and parsing."""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

from .model import Instruction


INSTRUCTION_RE = re.compile(
    r"^\s*([0-9a-fA-F]+):\s+([0-9a-fA-F]{8})\s+(.+?)\s*$"
)


def discover_objdump(explicit: str | None = None) -> str:
    """Find a usable MIPS objdump, preferring an explicit path."""

    candidates = [
        explicit,
        "tools/binutils/mips64-elf-objdump",
        "mips64-elf-objdump",
        "mips-linux-gnu-objdump",
        "objdump",
    ]
    for candidate in candidates:
        if not candidate:
            continue
        path = Path(candidate).expanduser()
        if path.is_file():
            return str(path)
        found = shutil.which(candidate)
        if found:
            return found
    raise FileNotFoundError(
        "could not find objdump; pass --objdump /path/to/mips64-elf-objdump"
    )


def parse_disassembly(text: str) -> list[Instruction]:
    """Parse GNU objdump instruction lines."""

    instructions: list[Instruction] = []
    for line in text.splitlines():
        match = INSTRUCTION_RE.match(line)
        if match:
            instructions.append(
                Instruction(
                    address=int(match.group(1), 16),
                    word=match.group(2).lower(),
                    assembly=match.group(3).strip(),
                )
            )
    return instructions


def dump_object(
    path: str | Path,
    *,
    objdump: str | None = None,
    symbol: str | None = None,
) -> tuple[str, list[Instruction]]:
    """Disassemble an object and return raw text plus parsed instructions."""

    executable = discover_objdump(objdump)
    command = [executable, "-d", str(path)]
    if symbol:
        command.append(f"--disassemble={symbol}")
    result = subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode:
        message = result.stderr.strip() or result.stdout.strip()
        raise RuntimeError(f"objdump failed for {path}: {message}")
    instructions = parse_disassembly(result.stdout)
    if not instructions:
        suffix = f" for symbol {symbol}" if symbol else ""
        raise RuntimeError(f"objdump produced no instructions{suffix}: {path}")
    return result.stdout, instructions
