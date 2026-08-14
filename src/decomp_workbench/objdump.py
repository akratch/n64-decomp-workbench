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
import struct
import subprocess
import tempfile
from collections.abc import Sequence
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from .elf_instructions import MINIMUM_ELIDED_RUN
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


@dataclass(frozen=True)
class ObjdumpProbe:
    """Measured GNU/MIPS capabilities for one executable."""

    executable: str
    compatible: bool
    version: str | None
    checks: tuple[tuple[str, bool], ...]
    error: str | None = None

    def as_dict(self) -> dict[str, object]:
        return {
            "compatible": self.compatible,
            "version": self.version,
            "checks": {name: passed for name, passed in self.checks},
            "error": self.error,
        }


def _mips_probe_object() -> bytes:
    """Return a tiny deterministic MIPS ELF32 object with one relocation.

    This is generated rather than shipped as an opaque binary so the doctor
    probe remains auditable and works from source checkouts and wheels alike.
    It exercises the exact format, symbol filtering, instruction syntax, and
    relocation syntax consumed by :func:`dump_object`.
    """

    def align(value: int, boundary: int = 4) -> int:
        return (value + boundary - 1) & ~(boundary - 1)

    text = struct.pack(">III", 0x0C000000, 0x03E00008, 0x00000000)
    relocation = struct.pack(">II", 0, (1 << 8) | 4)  # R_MIPS_26, symbol 1
    strings = b"\0probe_external\0probe_func\0"
    external_name = strings.index(b"probe_external")
    function_name = strings.index(b"probe_func")
    symbols = b"".join(
        (
            b"\0" * 16,
            struct.pack(">IIIBBH", external_name, 0, 0, 0x10, 0, 0),
            struct.pack(">IIIBBH", function_name, 0, len(text), 0x12, 0, 1),
        )
    )
    section_names = b"\0.text\0.rel.text\0.symtab\0.strtab\0.shstrtab\0"

    offset = 52
    text_offset = offset
    offset = align(text_offset + len(text))
    relocation_offset = offset
    offset = align(relocation_offset + len(relocation))
    symbols_offset = offset
    offset = align(symbols_offset + len(symbols))
    strings_offset = offset
    offset = align(strings_offset + len(strings))
    section_names_offset = offset
    section_headers_offset = align(section_names_offset + len(section_names))

    identifier = b"\x7fELF\x01\x02\x01\x00" + b"\0" * 8
    header = struct.pack(
        ">16sHHIIIIIHHHHHH",
        identifier,
        1,  # relocatable
        8,  # EM_MIPS
        1,
        0,
        0,
        section_headers_offset,
        0x10001007,  # o32, MIPS I
        52,
        0,
        0,
        40,
        6,
        5,
    )

    def section_name(name: bytes) -> int:
        return section_names.index(name)

    sections = b"".join(
        (
            b"\0" * 40,
            struct.pack(
                ">IIIIIIIIII",
                section_name(b".text"),
                1,
                0x6,
                0,
                text_offset,
                len(text),
                0,
                0,
                4,
                0,
            ),
            struct.pack(
                ">IIIIIIIIII",
                section_name(b".rel.text"),
                9,
                0,
                0,
                relocation_offset,
                len(relocation),
                3,
                1,
                4,
                8,
            ),
            struct.pack(
                ">IIIIIIIIII",
                section_name(b".symtab"),
                2,
                0,
                0,
                symbols_offset,
                len(symbols),
                4,
                1,
                4,
                16,
            ),
            struct.pack(
                ">IIIIIIIIII",
                section_name(b".strtab"),
                3,
                0,
                0,
                strings_offset,
                len(strings),
                0,
                0,
                1,
                0,
            ),
            struct.pack(
                ">IIIIIIIIII",
                section_name(b".shstrtab"),
                3,
                0,
                0,
                section_names_offset,
                len(section_names),
                0,
                0,
                1,
                0,
            ),
        )
    )
    image = bytearray(section_headers_offset + len(sections))
    image[: len(header)] = header
    image[text_offset : text_offset + len(text)] = text
    image[relocation_offset : relocation_offset + len(relocation)] = relocation
    image[symbols_offset : symbols_offset + len(symbols)] = symbols
    image[strings_offset : strings_offset + len(strings)] = strings
    image[section_names_offset : section_names_offset + len(section_names)] = (
        section_names
    )
    image[section_headers_offset:] = sections
    return bytes(image)


@lru_cache(maxsize=32)
def _probe_objdump_cached(executable: str, modified_ns: int, size: int) -> ObjdumpProbe:
    del modified_ns, size  # cache identity; content is read by the subprocess
    version: str | None = None
    checks = {
        "mips_elf32": False,
        "symbol_filter": False,
        "gnu_instruction_syntax": False,
        "mips_relocations": False,
    }
    try:
        version_result = subprocess.run(
            [executable, "--version"],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=3,
        )
        version_lines = (version_result.stdout or version_result.stderr).splitlines()
        version = version_lines[0].strip() if version_lines else None
        with tempfile.TemporaryDirectory(
            prefix="decomp-workbench-objdump-probe-"
        ) as tmp:
            probe = Path(tmp) / "mips-probe.o"
            probe.write_bytes(_mips_probe_object())
            result = subprocess.run(
                [
                    executable,
                    "-d",
                    "-r",
                    "-z",
                    "-j",
                    ".text",
                    str(probe),
                    "--disassemble=probe_func",
                ],
                check=False,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=3,
            )
        checks["mips_elf32"] = result.returncode == 0
        checks["symbol_filter"] = "<probe_func>:" in result.stdout
        instructions = parse_disassembly(result.stdout, symbol="probe_func")
        checks["gnu_instruction_syntax"] = [item.word for item in instructions] == [
            "0c000000",
            "03e00008",
            "00000000",
        ]
        checks["mips_relocations"] = bool(
            instructions
            and instructions[0].relocations
            and instructions[0].relocations[0].kind == "R_MIPS_26"
            and instructions[0].relocations[0].symbol == "probe_external"
        )
        compatible = all(checks.values())
        detail = (
            (result.stderr.strip() or result.stdout.strip()) if not compatible else ""
        )
        error = None if compatible else (detail.splitlines()[-1] if detail else None)
        return ObjdumpProbe(
            executable=executable,
            compatible=compatible,
            version=version,
            checks=tuple(checks.items()),
            error=error or (None if compatible else "capability probe failed"),
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        return ObjdumpProbe(
            executable=executable,
            compatible=False,
            version=version,
            checks=tuple(checks.items()),
            error=str(error),
        )


def probe_objdump(executable: str) -> ObjdumpProbe:
    """Measure whether ``executable`` satisfies the workbench contract."""

    path = Path(executable).resolve()
    stat = path.stat()
    return _probe_objdump_cached(str(path), stat.st_mtime_ns, stat.st_size)


def discover_objdump(explicit: str | None = None) -> str:
    """Find a capability-proven MIPS objdump, preferring an explicit path."""

    if explicit:
        path = Path(explicit).expanduser()
        if path.is_file() and os.access(path, os.X_OK):
            # Explicit wrappers are an advanced escape hatch and may only
            # understand project objects, not the synthetic probe. Doctor
            # still measures an explicitly supplied executable; ordinary
            # object commands let its real invocation be the referee.
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
    rejected: list[str] = []
    for candidate in candidates:
        path = Path(candidate).expanduser()
        candidate_path: str | None = None
        if path.is_file() and os.access(path, os.X_OK):
            candidate_path = str(path.resolve())
        else:
            candidate_path = shutil.which(candidate)
        if not candidate_path:
            continue
        probe = probe_objdump(candidate_path)
        if probe.compatible:
            return probe.executable
        rejected.append(f"{candidate_path}: {probe.error}")
    detail = f"; rejected incompatible tools: {'; '.join(rejected)}" if rejected else ""
    raise FileNotFoundError(
        "could not find a GNU-compatible MIPS objdump; install MIPS GNU "
        "binutils or pass --objdump /path/to/mips64-elf-objdump" + detail
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
    """Parse GNU objdump instruction lines, optionally for one symbol.

    When ``symbol`` has no exact match, a unique case-insensitive match is
    accepted: Pascal-era frontends (``upas``) fold identifiers to lower
    case, so a function authored as ``Foo`` disassembles as ``foo``. The
    fallback needs to see every symbol to know the match is unique, so it only
    fires on a whole-section dump -- which is what `_whole_section_pass`
    exists to hand it.
    """

    match_symbol = symbol
    if symbol is not None:
        names = [m.group("name") for m in map(SYMBOL_RE.match, text.splitlines()) if m]
        if symbol not in names:
            folded = [name for name in names if name.casefold() == symbol.casefold()]
            if len(folded) == 1:
                match_symbol = folded[0]
    relocations = parse_relocations(text)
    instructions: list[Instruction] = []
    selected = match_symbol is None
    for line in text.splitlines():
        symbol_match = SYMBOL_RE.match(line)
        if symbol_match:
            selected = (
                match_symbol is None or symbol_match.group("name") == match_symbol
            )
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


def anonymous_single_function(text: str, *, section: str = ".text") -> bool:
    """True when a section dump holds code but no symbol naming a function.

    IDO strips a local (``static``) function's symbol, and a decomp.me export
    ships exactly one function's worth of ``.text`` with nothing in the symbol
    table pointing at it. GNU objdump then labels the section itself, so the
    dump reads ``00000000 <.text>:`` and ``--disassemble=NAME`` matches
    nothing. This is the standard shape of an export target, not a broken
    object, which is why it gets a fallback rather than an error.

    The section label is required, not merely tolerated: a dump carrying
    instructions under *no* label at all is truncated or malformed output, and
    answering a symbol selection from it would turn a broken build into a
    confident positional verdict.
    """

    return symbol_labels(text) == (section,)


def stripped_symbol_fallback_warning(
    text: str,
    *,
    symbol: str | None,
    name: str,
    section: str = ".text",
) -> str | None:
    """Warn that ``--function`` was answered by a whole-section compare.

    The selector was honoured in the only way the object allows. Saying so is
    still required: the comparison that follows is positional over the whole
    section, so it is only meaningful when the section really does hold the
    one function the reader named.
    """

    if symbol is None or not anonymous_single_function(text, section=section):
        return None
    return (
        f"{name} has no symbol for {symbol!r} - its {section} is one "
        "function's worth of code with the symbol stripped, which is normal "
        "for a decomp.me export and for an IDO static function. Comparing "
        f"the whole {section} section positionally instead. Omit --function "
        "to select this path explicitly."
    )


def parse_selected_disassembly(
    text: str, *, symbol: str | None, section: str = ".text"
) -> list[Instruction]:
    """Select one symbol from dump text, or the whole section when it has none.

    The text form of the same fallback `dump_object` performs on an object, so
    the ``*-dumps`` commands and the object commands agree about what a
    stripped export means. See `anonymous_single_function`.
    """

    instructions = parse_disassembly(text, symbol=symbol)
    if instructions or symbol is None:
        return instructions
    if not anonymous_single_function(text, section=section):
        return instructions
    return parse_disassembly(text, symbol=None)


def selection_warnings(
    target_text: str,
    candidate_text: str,
    *,
    symbol: str | None,
    target_name: str,
    candidate_name: str,
    section: str = ".text",
) -> list[str]:
    """Return every warning about what the selector actually selected.

    `compare`, `view`, and `diagnose` each disassemble the same way and must
    say the same thing about the result, so they share one list rather than
    three call sites that can drift. Order is deliberate: a fallback retracts
    more than a cross-function mismatch does.
    """

    return [
        item
        for item in (
            stripped_symbol_fallback_warning(
                target_text, symbol=symbol, name=target_name, section=section
            ),
            stripped_symbol_fallback_warning(
                candidate_text, symbol=symbol, name=candidate_name, section=section
            ),
            cross_function_warning(
                target_text, candidate_text, symbol=symbol, section=section
            ),
        )
        if item
    ]


def symbol_selection_error(
    symbol: str | None,
    *,
    inputs: Sequence[tuple[str, str]],
    missing: Sequence[str] = (),
) -> str:
    """Return the error for a selection that matched no instructions.

    A typo and a case slip used to produce the same opaque sentence, so the
    reader could not tell which mistake they had made. Listing what each input
    actually defines turns both into a one-glance fix, and naming
    case-sensitivity explicitly covers the case the list alone does not make
    obvious when the names are long.
    """

    # `missing` is for the caller that already knows which input failed --
    # `dump_object` reports the unfiltered section dump here precisely because
    # the filtered one was empty, so re-deriving emptiness from it would
    # contradict the fact that brought us here.
    empty = [
        (name, text)
        for name, text in inputs
        if name in missing or not parse_disassembly(text, symbol=symbol)
    ]
    listed = ", ".join(name for name, _ in empty) or ", ".join(
        name for name, _ in inputs
    )
    if symbol is None:
        return (
            f"no GNU-style objdump instruction lines in {listed or 'the inputs'}; "
            "expected lines like `  1c: 8f998010 lw t9,-32752(gp)`. "
            f"See {TROUBLESHOOTING_NO_INSTRUCTIONS}"
        )
    names = listed or "the inputs"
    lines = [f"symbol {symbol!r} produced no instructions in {names}."]
    lines.extend(
        f"  {name} defines: {_name_list(symbol_labels(text))}" for name, text in inputs
    )
    if any(anonymous_single_function(text) for _, text in empty):
        lines.append(
            "  That object defines no function symbols at all, so no name "
            "can select in it. Omit --function to compare the whole section "
            "positionally."
        )
    lines.append(f"  Names are case-sensitive. See {TROUBLESHOOTING_NO_INSTRUCTIONS}")
    return "\n".join(lines)


def trim_function_padding(instructions: list[Instruction]) -> list[Instruction]:
    """Drop unreachable zero padding after a final ``jr ra`` delay slot.

    Assembly-defined symbols commonly have no ELF size.  In that case GNU
    objdump's ``--disassemble=SYMBOL`` output can run from the symbol through
    the end of the section and include alignment zeroes after the function.
    A MIPS return owns exactly one delay-slot instruction, so later zero words
    are section padding rather than part of that function -- provided there
    are at least :data:`~decomp_workbench.elf_instructions.MINIMUM_ELIDED_RUN`
    of them. A single trailing zero word is a real ``nop`` GNU objdump's own
    default disassembly still prints, not padding it elides; trimming it took
    one real instruction off a campaign object whose ``.text`` needed no
    alignment filler at all. See ``elf_instructions`` for the measurement.
    """

    last_return = None
    for index, instruction in enumerate(instructions):
        assembly = instruction.assembly.replace("$", "")
        if re.match(r"^jr\s+ra(?:\s|$)", assembly):
            last_return = index
    if last_return is None or last_return + 2 >= len(instructions):
        return instructions
    trailing = instructions[last_return + 2 :]
    if len(trailing) >= MINIMUM_ELIDED_RUN and all(
        instruction.word == "00000000" for instruction in trailing
    ):
        return instructions[: last_return + 2]
    return instructions


def true_instruction_count(instructions: Sequence[Instruction]) -> int:
    """Return the real instruction count, blind to trailing `.text` padding.

    The disassembly-text equivalent of
    :func:`decomp_workbench.elf_instructions.true_instruction_count`, for
    callers that hold parsed instructions but no path to an object file to
    read directly (retained ``--dumps`` text has no such path). Both apply the
    identical trimming rule, so a caller that has *both* an object and its
    already-parsed instructions should get the same number from either -- this
    one is the fallback when only the text is available.
    """

    return len(trim_function_padding(list(instructions)))


def _run_objdump(
    executable: str,
    path: str | Path,
    *,
    section: str,
    symbol: str | None,
) -> subprocess.CompletedProcess[str]:
    """Run one disassembly, optionally narrowed to a single symbol."""

    command = [executable, "-d", "-r", "-z", "-j", section, str(path)]
    if symbol:
        command.append(f"--disassemble={symbol}")
    return subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def _whole_section_pass(
    executable: str,
    path: str | Path,
    *,
    section: str,
    symbol: str,
) -> tuple[str, list[Instruction]]:
    """Re-dump the whole section once, and answer both questions with it.

    ``--disassemble=NAME`` filters case-sensitively inside objdump and prints
    *nothing* when it matches nothing: no error, no symbol headers, an empty
    stream. Two independent problems follow from that, and both are solved by
    the same text, so they are solved by the same subprocess:

    * a Pascal-era frontend (``upas``) folds identifiers to lower case, so a
      function authored as ``Foo`` disassembles as ``foo`` and the filtered run
      finds nothing. `parse_disassembly` accepts a *unique* case-insensitive
      match, and it can only do that when it can see every symbol -- which is
      what this pass gives it.
    * when no such match exists either, the error has to say what the object
      really defines. Built from the filtered stream it said "defines: no
      symbols" about an object holding the function the reader misspelled,
      pointing at a broken build instead of at a typo.

    Two separate retries would have doubled the objdump cost of every miss, so
    this is deliberately one call whose text is returned alongside its parse.
    """

    retry = _run_objdump(executable, path, section=section, symbol=None)
    if retry.returncode:
        return "", []
    return retry.stdout, parse_disassembly(retry.stdout, symbol=symbol)


def dump_object(
    path: str | Path,
    *,
    objdump: str | None = None,
    symbol: str | None = None,
    section: str = ".text",
) -> tuple[str, list[Instruction]]:
    """Disassemble an object and return raw text plus parsed instructions."""

    executable = discover_objdump(objdump)
    result = _run_objdump(executable, path, section=section, symbol=symbol)
    if result.returncode:
        raise RuntimeError(_objdump_failure(path, result))
    instructions = parse_disassembly(result.stdout, symbol=symbol)
    if instructions:
        return result.stdout, instructions
    evidence = result.stdout
    if symbol:
        # One unfiltered pass answers both "is this a case slip we can honour?"
        # and "what does this object actually define?". See its docstring.
        section_text, retried = _whole_section_pass(
            executable, path, section=section, symbol=symbol
        )
        if retried:
            return section_text, retried
        if section_text and anonymous_single_function(section_text, section=section):
            # The object cannot name this function because nothing in it names
            # any function. Refusing here sent readers to "produced no
            # instructions ... defines: .text", which reads like an object
            # with no code in it. Callers surface
            # `stripped_symbol_fallback_warning` for the same text.
            whole_section = parse_disassembly(section_text, symbol=None)
            if whole_section:
                return section_text, whole_section
        evidence = section_text or result.stdout
    raise RuntimeError(
        symbol_selection_error(
            symbol, inputs=((str(path), evidence),), missing=(str(path),)
        )
    )


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
