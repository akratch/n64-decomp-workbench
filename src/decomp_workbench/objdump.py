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
from collections.abc import Sequence
from pathlib import Path

from .model import Instruction, Relocation

#: How many symbol names an error lists before eliding the rest. Enough to
#: spot a case or spelling slip, short enough that a whole-section dump does
#: not bury the sentence that says what to do.
SYMBOL_LIST_LIMIT = 8

TROUBLESHOOTING_NO_INSTRUCTIONS = (
    "docs/troubleshooting.md#objdump-produced-no-instructions"
)

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


def symbol_labels(text: str) -> tuple[str, ...]:
    """Return every ``<name>:`` label in disassembly, in emission order.

    Deliberately separate from `parse_disassembly`: what a dump *defines* is a
    question about the input, asked before anything is compared, and keeping it
    out of the parser keeps the parser one job.
    """

    return tuple(
        match.group("name")
        for line in text.splitlines()
        if (match := SYMBOL_RE.match(line))
    )


def _name_list(names: Sequence[str]) -> str:
    shown = list(names[:SYMBOL_LIST_LIMIT])
    remainder = len(names) - len(shown)
    joined = ", ".join(shown) if shown else "no symbols"
    return f"{joined}, ... (+{remainder} more)" if remainder > 0 else joined


def cross_function_warning(
    target_text: str,
    candidate_text: str,
    *,
    symbol: str | None,
    section: str = ".text",
) -> str | None:
    """Return a warning when two dumps name one function each, and differ.

    Without ``--function`` the comparison is positional over the whole section,
    which is correct and useful when both objects hold the same function. When
    each side holds exactly one *differently named* function, the same code
    silently diffs two unrelated bodies and reports a confident verdict about
    the result. That is the one shape where silence produces a wrong answer
    rather than a coarse one, so it is the one shape that warns.
    """

    if symbol is not None:
        return None
    target = symbol_labels(target_text)
    candidate = symbol_labels(candidate_text)
    if len(target) != 1 or len(candidate) != 1 or target[0] == candidate[0]:
        return None
    return (
        f"target defines {target[0]!r} but candidate defines {candidate[0]!r} - "
        f"comparing the whole {section} section positionally, not one "
        "function. Pass --function to select a single symbol explicitly."
    )


def symbol_selection_error(
    symbol: str | None,
    *,
    inputs: Sequence[tuple[str, str]],
) -> str:
    """Return the error for a selection that matched no instructions.

    A typo and a case slip used to produce the same opaque sentence, so the
    reader could not tell which mistake they had made. Listing what each input
    actually defines turns both into a one-glance fix, and naming
    case-sensitivity explicitly covers the case the list alone does not make
    obvious when the names are long.
    """

    empty = [
        (name, text)
        for name, text in inputs
        if not parse_disassembly(text, symbol=symbol)
    ]
    if symbol is None:
        names = ", ".join(name for name, _ in empty) or "the inputs"
        return (
            f"no GNU-style objdump instruction lines in {names}; expected "
            "lines like `  1c: 8f998010 lw t9,-32752(gp)`. "
            f"See {TROUBLESHOOTING_NO_INSTRUCTIONS}"
        )
    names = ", ".join(name for name, _ in empty) or "the inputs"
    lines = [f"symbol {symbol!r} produced no instructions in {names}."]
    lines.extend(
        f"  {name} defines: {_name_list(symbol_labels(text))}" for name, text in inputs
    )
    lines.append(f"  Names are case-sensitive. See {TROUBLESHOOTING_NO_INSTRUCTIONS}")
    return "\n".join(lines)


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
        encoding="utf-8",
        errors="replace",
    )
    if result.returncode:
        raise RuntimeError(_objdump_failure(path, result))
    instructions = parse_disassembly(result.stdout, symbol=symbol)
    if not instructions:
        raise RuntimeError(
            symbol_selection_error(symbol, inputs=((str(path), result.stdout),))
        )
    return result.stdout, instructions


def _objdump_failure(path: str | Path, result: subprocess.CompletedProcess[str]) -> str:
    """Explain an objdump failure before quoting it.

    Raw passthrough glued two unrelated-looking objdump lines together and left
    the reader to infer the cause. The most common one by far -- a path that is
    not an object at all, usually because the build never produced one -- has a
    recognizable signature, so name it and keep the tool's own words beneath.
    """

    message = (result.stderr.strip() or result.stdout.strip()) or "no output"
    quoted = "\n".join(f"  {line}" for line in message.splitlines())
    if "file format not recognized" in message:
        return (
            f"objdump failed for {path}: this does not look like a compiled "
            "MIPS ELF object (check the path, and that the build actually "
            f"produced an object file). objdump said:\n{quoted}"
        )
    return f"objdump failed for {path}: objdump said:\n{quoted}"
