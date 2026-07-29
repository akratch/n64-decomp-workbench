"""Objdump discovery, invocation, and parsing.

GNU objdump prints relocations on a line following the affected instruction.
The parser makes those relocations part of the instruction model so comparison
can ignore only linker-controlled fields instead of broadly masking every
immediate.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path

from .model import Instruction, Relocation

INSTRUCTION_RE = re.compile(r"^\s*([0-9a-fA-F]+):\s+([0-9a-fA-F]{8})\s+(.+?)\s*$")
RELOCATION_RE = re.compile(
    r"^\s*([0-9a-fA-F]+):?\s+"
    r"(R_MIPS_[A-Za-z0-9_]+)"
    r"(?:\s+(.+?))?\s*$"
)
SYMBOL_RE = re.compile(r"^\s*[0-9a-fA-F]+\s+<(?P<name>[^>]+)>:\s*$")


def discover_objdump(explicit: str | None = None) -> str:
    """Find a usable MIPS objdump, preferring an explicit path."""

    if explicit:
        path = Path(explicit).expanduser()
        if path.is_file() and os.access(path, os.X_OK):
            return str(path.resolve())
        found = shutil.which(explicit)
        if found:
            return found
        raise FileNotFoundError(
            f"explicit objdump does not exist or is not executable: {explicit}"
        )

    candidates = [
        "tools/binutils/mips64-elf-objdump",
        "mips64-elf-objdump",
        "mips-linux-gnu-objdump",
        "objdump",
    ]
    for candidate in candidates:
        path = Path(candidate).expanduser()
        if path.is_file() and os.access(path, os.X_OK):
            return str(path.resolve())
        found = shutil.which(candidate)
        if found:
            return found
    raise FileNotFoundError(
        "could not find objdump; pass --objdump /path/to/mips64-elf-objdump"
    )


def parse_relocations(text: str) -> dict[int, tuple[Relocation, ...]]:
    """Parse GNU objdump ``-r`` lines, grouped by section offset."""

    grouped: dict[int, list[Relocation]] = {}
    for line in text.splitlines():
        match = RELOCATION_RE.match(line)
        if not match:
            continue
        offset = int(match.group(1), 16)
        symbol = match.group(3)
        grouped.setdefault(offset, []).append(
            Relocation(
                offset=offset,
                kind=match.group(2),
                symbol=symbol.strip() if symbol else None,
            )
        )
    return {offset: tuple(items) for offset, items in grouped.items()}


def parse_disassembly(text: str, *, symbol: str | None = None) -> list[Instruction]:
    """Parse GNU objdump instruction lines, optionally for one symbol."""

    relocations = parse_relocations(text)
    instructions: list[Instruction] = []
    selected = symbol is None
    for line in text.splitlines():
        symbol_match = SYMBOL_RE.match(line)
        if symbol_match:
            selected = symbol is None or symbol_match.group("name") == symbol
            continue
        if not selected:
            continue
        match = INSTRUCTION_RE.match(line)
        if match:
            address = int(match.group(1), 16)
            instructions.append(
                Instruction(
                    address=address,
                    word=match.group(2).lower(),
                    assembly=match.group(3).strip(),
                    relocations=relocations.get(address, ()),
                )
            )
    return trim_function_padding(instructions) if symbol else instructions


def trim_function_padding(instructions: list[Instruction]) -> list[Instruction]:
    """Drop unreachable zero padding after a final ``jr ra`` delay slot.

    Assembly-defined symbols commonly have no ELF size.  In that case GNU
    objdump's ``--disassemble=SYMBOL`` output can run from the symbol through
    the end of the section and include alignment zeroes after the function.
    A MIPS return owns exactly one delay-slot instruction, so later zero words
    are section padding rather than part of that function.
    """

    last_return = None
    for index, instruction in enumerate(instructions):
        assembly = instruction.assembly.replace("$", "")
        if re.match(r"^jr\s+ra(?:\s|$)", assembly):
            last_return = index
    if last_return is None or last_return + 2 >= len(instructions):
        return instructions
    trailing = instructions[last_return + 2 :]
    if all(instruction.word == "00000000" for instruction in trailing):
        return instructions[: last_return + 2]
    return instructions


def dump_object(
    path: str | Path,
    *,
    objdump: str | None = None,
    symbol: str | None = None,
    section: str = ".text",
) -> tuple[str, list[Instruction]]:
    """Disassemble an object and return raw text plus parsed instructions."""

    executable = discover_objdump(objdump)
    command = [executable, "-d", "-r", "-z", "-j", section, str(path)]
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
    instructions = parse_disassembly(result.stdout, symbol=symbol)
    if not instructions:
        suffix = f" for symbol {symbol}" if symbol else ""
        raise RuntimeError(f"objdump produced no instructions{suffix}: {path}")
    return result.stdout, instructions
