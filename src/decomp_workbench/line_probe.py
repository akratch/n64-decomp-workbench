"""Line-assignment probe: does statement line assignment own a schedule?

This module automates the decisive drawbitmap-campaign experiment for a
stubborn ``schedule-mismatch`` residue: the same instruction multiset in a
different order, invariant under every compiler flag and era tried. Splitting
a single-line macro-expansion statement onto separate physical lines is a
TOKEN-IDENTICAL change; if it moves the schedule, statement line assignment
(not the compiler binary) owns the residual, because IDO's cfe records a
per-statement line number and uopt/ugen honor line boundaries as scheduling
barriers even at ``-g0``. See ``docs/field-guide.md`` lever 3 (the ``-g0``
diagnostic) for this probe's sibling and ``docs/line-assignment-probe.md`` for
the worked drawbitmap numbers (59 diff words -> 0, byte-exact, every IDO era
identical given the same ``.i``).

Three deterministic variants are compiled from one preprocessed ``.i``:

* ``baseline`` - untouched.
* ``split-statements`` - a newline is inserted after each ``;`` found at
  brace-depth >= 1, outside strings/char literals/comments, and outside a
  ``for(;;)`` header, but only on physical lines longer than
  ``--split-threshold`` characters (default 400). This is the token-identical
  reflow that decided the drawbitmap campaign.
* ``global-shift`` - ``--shift-lines`` (default 20) blank lines are inserted
  at the top. A pure line-number relabeling with no statement regrouping;
  it is the control and must never move the object.

The comparison is over raw instruction *words* (4-byte chunks of the
compiled ``.text`` section, or of one function's byte range when
``--function`` is given), never a disassembly: the campaign's finding was
about which 4-byte words land at which position, not about mnemonics.
"""

from __future__ import annotations

import itertools
import struct
import tempfile
import time
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .artifacts import DEFAULT_STREAM_LIMIT, capture_streams
from .campaign import CompilerTimeoutError, run_compiler
from .model import display_path
from .pass_adapter import render_pass_command

LINE_PROBE_SCHEMA = "decomp-workbench-line-probe-v1"

DEFAULT_SPLIT_THRESHOLD = 400
DEFAULT_SHIFT_LINES = 20
DEFAULT_WORK_DIR = ".decomp-workbench/probe-lines"

VARIANT_NAMES: tuple[str, ...] = ("baseline", "split-statements", "global-shift")

VARIANT_DESCRIPTIONS: dict[str, str] = {
    "baseline": "untouched preprocessed source",
    "split-statements": (
        "on physical lines longer than --split-threshold, insert a newline "
        "after each ';' at brace-depth>=1, outside strings/char literals/"
        "comments, and outside a for(;;) header - token-identical"
    ),
    "global-shift": (
        "insert --shift-lines blank lines at the top (control: must never "
        "change the compiled object)"
    ),
    "tie": (
        "wrap each --tie STATEMENT=LINE statement in a '#line LINE' / "
        "restore pair, reassigning only that statement's line number - "
        "token-identical"
    ),
}

#: Text explaining where a `.i` comes from, for `--help` and error messages.
PREPROCESSED_INPUT_HELP = (
    "a preprocessed C translation unit ('cc -E unit.c > unit.i', or what an "
    "IDO-style driver retains alongside its normal compile with -K)"
)

ELF_MAGIC = b"\x7fELF"
SHT_SYMTAB = 2
STT_FUNC = 2


class LineProbeError(ValueError):
    """A user-facing line-probe failure that must never show a traceback."""


class ElfFormatError(LineProbeError):
    """The compiled artifact could not be read as an ELF object."""


# ---------------------------------------------------------------------------
# Variant generation
# ---------------------------------------------------------------------------


def global_shift(text: str, *, blank_lines: int = DEFAULT_SHIFT_LINES) -> str:
    """Prepend `blank_lines` blank lines: a pure line-number relabeling."""

    if blank_lines < 0:
        raise LineProbeError("--shift-lines must be non-negative")
    return ("\n" * blank_lines) + text


def split_statement_lines(
    text: str, *, threshold: int = DEFAULT_SPLIT_THRESHOLD
) -> str:
    """Insert a newline after each qualifying ``;`` on an overlong line.

    A small, honest tokenizer walks the text once, tracking string and char
    literals, line and block comments, brace depth, and whether the current
    parenthesis group is a ``for (...)`` header - the one place a bare ``;``
    is punctuation, not a statement terminator. Known approximations:
    trigraphs and backslash-newline line continuations outside literals are
    not special-cased (a preprocessor normally resolves both before emitting
    a ``.i``), and a string prefix like ``L"..."`` or ``u8"..."`` is handled
    correctly only because the prefix letters are ordinary identifier
    characters that do not themselves open the literal.
    """

    if threshold <= 0:
        raise LineProbeError("--split-threshold must be positive")

    brace_depth = 0
    paren_stack: list[bool] = []  # True: this paren group is a for(...) header.
    current_word = ""
    in_string = False
    in_char = False
    in_block_comment = False

    out_lines: list[str] = []
    for line in text.splitlines(keepends=True):
        bare = line.rstrip("\n").rstrip("\r")
        eligible = len(bare) > threshold
        in_line_comment = False  # a line comment never continues past its line
        buffer: list[str] = []
        index = 0
        length = len(line)
        while index < length:
            char = line[index]
            nxt = line[index + 1] if index + 1 < length else ""
            if in_block_comment:
                buffer.append(char)
                if char == "*" and nxt == "/":
                    buffer.append(nxt)
                    index += 2
                    in_block_comment = False
                    continue
                index += 1
                continue
            if in_line_comment:
                buffer.append(char)
                index += 1
                continue
            if in_string:
                buffer.append(char)
                if char == "\\" and nxt:
                    buffer.append(nxt)
                    index += 2
                    continue
                if char == '"':
                    in_string = False
                index += 1
                continue
            if in_char:
                buffer.append(char)
                if char == "\\" and nxt:
                    buffer.append(nxt)
                    index += 2
                    continue
                if char == "'":
                    in_char = False
                index += 1
                continue
            if char == "/" and nxt == "*":
                in_block_comment = True
                buffer.append(char)
                current_word = ""
                index += 1
                continue
            if char == "/" and nxt == "/":
                in_line_comment = True
                buffer.append(char)
                current_word = ""
                index += 1
                continue
            if char == '"':
                in_string = True
                buffer.append(char)
                current_word = ""
                index += 1
                continue
            if char == "'":
                in_char = True
                buffer.append(char)
                current_word = ""
                index += 1
                continue
            if char.isalnum() or char == "_":
                current_word += char
                buffer.append(char)
                index += 1
                continue
            if char == "(":
                paren_stack.append(current_word == "for")
                buffer.append(char)
                current_word = ""
                index += 1
                continue
            if char == ")":
                if paren_stack:
                    paren_stack.pop()
                buffer.append(char)
                current_word = ""
                index += 1
                continue
            if char == "{":
                brace_depth += 1
                buffer.append(char)
                current_word = ""
                index += 1
                continue
            if char == "}":
                brace_depth = max(0, brace_depth - 1)
                buffer.append(char)
                current_word = ""
                index += 1
                continue
            if char == ";":
                buffer.append(char)
                current_word = ""
                inside_for_header = bool(paren_stack) and paren_stack[-1]
                if eligible and brace_depth >= 1 and not inside_for_header:
                    buffer.append("\n")
                index += 1
                continue
            # Ordinary punctuation or whitespace. Whitespace must not clear
            # `current_word`, or "for (" (with a space before the paren)
            # would never be recognized as a for-header.
            if not char.isspace():
                current_word = ""
            buffer.append(char)
            index += 1
        out_lines.append("".join(buffer))
    return "".join(out_lines)


def tie_statement_lines(text: str, ties: Sequence[tuple[int, int]]) -> str:
    """Reassign each tied statement's line number via a ``#line`` pair.

    Each ``(statement_line, assigned_line)`` pair wraps the 1-based
    ``statement_line`` of the original text in ``#line assigned_line`` and a
    restoring ``#line statement_line + 1``, so only that one statement's
    debug line number changes and every later statement keeps its original
    number. Both numbers refer to the ORIGINAL text, which is what makes
    several ties compose without arithmetic on the caller's side.

    The assigned number is deliberately *not* bounded by the input's length: a
    tie names the number a statement must carry, and that number may sit past
    the end of the file (or on a line the reflow never occupies). The statement
    number is bounded, because it addresses a physical line that must exist,
    must not be blank, and must not itself be a preprocessing directive - none
    of those carry a statement for `cfe` to number.
    """

    lines = text.splitlines(keepends=True)
    seen: dict[int, int] = {}
    for statement_line, assigned_line in ties:
        if assigned_line < 1:
            raise LineProbeError(
                f"--tie {statement_line}={assigned_line}: the assigned line "
                "number must be 1 or greater"
            )
        if statement_line < 1 or statement_line > len(lines):
            raise LineProbeError(
                f"--tie {statement_line}={assigned_line}: statement line "
                f"{statement_line} is outside the 1..{len(lines)} input range"
            )
        if statement_line in seen:
            raise LineProbeError(
                f"--tie lists statement line {statement_line} twice "
                f"(={seen[statement_line]} and ={assigned_line}); one "
                "statement can only be tied to one line number"
            )
        seen[statement_line] = assigned_line
        stripped = lines[statement_line - 1].strip()
        if not stripped or stripped.startswith("#"):
            what = "blank" if not stripped else "a preprocessing directive"
            raise LineProbeError(
                f"--tie {statement_line}={assigned_line}: input line "
                f"{statement_line} is {what}, so it carries no statement to "
                "reassign; tie the line the statement starts on"
            )
    out: list[str] = []
    by_line = seen
    for index, line in enumerate(lines, start=1):
        assigned = by_line.get(index)
        if assigned is None:
            out.append(line)
            continue
        if not line.endswith("\n"):
            line += "\n"
        out.append(f"#line {assigned}\n")
        out.append(line)
        out.append(f"#line {index + 1}\n")
    return "".join(out)


def generate_variants(
    text: str,
    *,
    split_threshold: int = DEFAULT_SPLIT_THRESHOLD,
    shift_lines: int = DEFAULT_SHIFT_LINES,
    ties: Sequence[tuple[int, int]] | None = None,
) -> dict[str, str]:
    """Return the deterministic variant source texts, baseline first."""

    variants = {
        "baseline": text,
        "split-statements": split_statement_lines(text, threshold=split_threshold),
        "global-shift": global_shift(text, blank_lines=shift_lines),
    }
    if ties:
        variants["tie"] = tie_statement_lines(text, ties)
    return variants


# ---------------------------------------------------------------------------
# Compiling one variant
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class VariantCompile:
    """One variant's compile command, outcome, and retained evidence."""

    name: str
    command: list[str]
    source_path: str
    object_path: str | None
    returncode: int
    duration_seconds: float
    stdout_preview: str
    stderr_preview: str
    stdout_path: str
    stderr_path: str

    @property
    def compiled(self) -> bool:
        return self.returncode == 0 and self.object_path is not None


def compile_variant(
    name: str,
    source_text: str,
    *,
    run_dir: Path,
    compile_template: str,
    compile_cwd: Path,
    environment: dict[str, str],
    timeout: float,
    stream_limit: int,
    artifact_dir: str | Path | None,
) -> VariantCompile:
    """Write one variant's source, compile it, and retain every stream.

    The variant directory is never removed by this function, on success or
    failure: it is the run directory's evidence, and a failed compile's
    stderr must remain readable at the path the error message names.
    """

    variant_dir = run_dir / name
    variant_dir.mkdir(parents=True, exist_ok=True)
    source_path = variant_dir / "variant.i"
    source_path.write_text(source_text, encoding="utf-8")
    object_path = variant_dir / "variant.o"
    command = render_pass_command(
        compile_template,
        input_path=source_path,
        output_path=object_path,
        work_path=variant_dir,
    )
    started = time.monotonic()
    try:
        process = run_compiler(
            command,
            environment=environment,
            compile_cwd=compile_cwd,
            timeout=timeout,
        )
        returncode = process.returncode
        stdout, stderr = process.stdout, process.stderr
    except CompilerTimeoutError as error:
        returncode = 124
        stdout, stderr = error.stdout, f"{error.stderr}\n{error}".strip()
    duration = time.monotonic() - started

    # The full streams are always retained in the run directory itself,
    # independent of --artifact-dir: the run directory is the durable
    # evidence a failed compile's error message points at.
    stdout_path = variant_dir / "compile.stdout.txt"
    stderr_path = variant_dir / "compile.stderr.txt"
    stdout_path.write_text(stdout, encoding="utf-8")
    stderr_path.write_text(stderr, encoding="utf-8")
    streams = capture_streams(
        stdout,
        stderr,
        limit=stream_limit,
        artifact_dir=artifact_dir,
        stem=name,
    )
    compiled = returncode == 0 and object_path.is_file()
    return VariantCompile(
        name=name,
        command=command,
        source_path=str(source_path),
        object_path=str(object_path) if compiled else None,
        returncode=returncode,
        duration_seconds=duration,
        stdout_preview=streams.stdout,
        stderr_preview=streams.stderr,
        stdout_path=str(stdout_path),
        stderr_path=str(stderr_path),
    )


# ---------------------------------------------------------------------------
# Minimal ELF32/ELF64 section and symbol-table reader
#
# Word-level comparison needs the compiled `.text` bytes - and, when
# --function is given, one symbol's byte range within it - without shelling
# out to objdump and without depending on any non-stdlib package. The parser
# below reads exactly the section-header table and (optionally) the symbol
# table; it does not interpret instructions, relocations, or program headers.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _Section:
    index: int
    name: str
    kind: int
    addr: int
    offset: int
    size: int
    link: int


@dataclass(frozen=True)
class _Symbol:
    name: str
    value: int
    size: int
    info: int
    shndx: int

    @property
    def kind(self) -> int:
        return self.info & 0xF


@dataclass(frozen=True)
class ObjectWindow:
    """The compared byte range: its words and a human-readable provenance."""

    words: tuple[bytes, ...]
    source: str
    byte_length: int


def _cstr(blob: bytes, offset: int) -> str:
    if offset >= len(blob):
        return ""
    end = blob.find(b"\x00", offset)
    if end < 0:
        end = len(blob)
    return blob[offset:end].decode("utf-8", errors="replace")


def _chunk_words(data: bytes) -> tuple[bytes, ...]:
    """Split bytes into 4-byte words; a trailing short chunk is kept as-is.

    A well-formed MIPS .text region is a multiple of 4 bytes; a short final
    chunk should not occur in practice and is kept rather than silently
    dropped so a malformed window is visible in the word count.
    """

    return tuple(data[i : i + 4] for i in range(0, len(data), 4))


def _parse_elf_sections(data: bytes) -> tuple[str, bool, list[_Section]]:
    if len(data) < 20 or data[:4] != ELF_MAGIC:
        raise ElfFormatError(
            "does not look like an ELF object (missing 0x7f 'ELF' magic); "
            "the compile command must produce a real relocatable object for "
            "word-level comparison"
        )
    ei_class = data[4]
    ei_data = data[5]
    if ei_class not in (1, 2):
        raise ElfFormatError(f"unsupported ELF class byte {ei_class!r}")
    if ei_data not in (1, 2):
        raise ElfFormatError(f"unsupported ELF data-encoding byte {ei_data!r}")
    endian = "<" if ei_data == 1 else ">"
    is64 = ei_class == 2
    if is64:
        header_fmt = endian + "HHIQQQIHHHHHH"
        section_fmt = endian + "IIQQQQIIQQ"
    else:
        header_fmt = endian + "HHIIIIIHHHHHH"
        section_fmt = endian + "IIIIIIIIII"
    header_size = struct.calcsize(header_fmt)
    if len(data) < 16 + header_size:
        raise ElfFormatError("truncated ELF header")
    (
        _e_type,
        _e_machine,
        _e_version,
        _e_entry,
        _e_phoff,
        e_shoff,
        _e_flags,
        _e_ehsize,
        _e_phentsize,
        _e_phnum,
        e_shentsize,
        e_shnum,
        e_shstrndx,
    ) = struct.unpack_from(header_fmt, data, 16)
    if e_shoff == 0 or e_shnum == 0:
        raise ElfFormatError(
            "object has no section-header table (stripped, or not a "
            "relocatable/linked object)"
        )
    section_size = struct.calcsize(section_fmt)
    raw: list[tuple[int, int, int, int, int, int]] = []
    for index in range(e_shnum):
        offset = e_shoff + index * e_shentsize
        if offset + section_size > len(data):
            raise ElfFormatError("truncated ELF section-header table")
        fields = struct.unpack_from(section_fmt, data, offset)
        sh_name, sh_type, _sh_flags, sh_addr, sh_offset, sh_size = fields[:6]
        sh_link = fields[6]
        raw.append((sh_name, sh_type, sh_addr, sh_offset, sh_size, sh_link))
    if e_shstrndx >= len(raw):
        raise ElfFormatError("invalid section-name string table index")
    shstr_offset, shstr_size = raw[e_shstrndx][3], raw[e_shstrndx][4]
    if shstr_offset + shstr_size > len(data):
        raise ElfFormatError("truncated section-name string table")
    shstrtab = data[shstr_offset : shstr_offset + shstr_size]
    sections = []
    for index, entry in enumerate(raw):
        sh_name, sh_type, sh_addr, sh_offset, sh_size, sh_link = entry
        sections.append(
            _Section(
                index=index,
                name=_cstr(shstrtab, sh_name),
                kind=sh_type,
                addr=sh_addr,
                offset=sh_offset,
                size=sh_size,
                link=sh_link,
            )
        )
    return endian, is64, sections


def _parse_symbols(
    data: bytes, *, endian: str, is64: bool, symtab: _Section, sections: list[_Section]
) -> list[_Symbol]:
    if symtab.link >= len(sections):
        raise ElfFormatError("symbol table's linked string-table index is out of range")
    strtab = sections[symtab.link]
    if strtab.offset + strtab.size > len(data):
        raise ElfFormatError("truncated symbol string table")
    strtab_blob = data[strtab.offset : strtab.offset + strtab.size]
    sym_fmt = (endian + "IBBHQQ") if is64 else (endian + "IIIBBH")
    entry_size = struct.calcsize(sym_fmt)
    count = symtab.size // entry_size
    symbols: list[_Symbol] = []
    for i in range(count):
        offset = symtab.offset + i * entry_size
        if offset + entry_size > len(data):
            raise ElfFormatError("truncated symbol table entry")
        if is64:
            st_name, st_info, _st_other, st_shndx, st_value, st_size = (
                struct.unpack_from(sym_fmt, data, offset)
            )
        else:
            st_name, st_value, st_size, st_info, _st_other, st_shndx = (
                struct.unpack_from(sym_fmt, data, offset)
            )
        symbols.append(
            _Symbol(
                name=_cstr(strtab_blob, st_name),
                value=st_value,
                size=st_size,
                info=st_info,
                shndx=st_shndx,
            )
        )
    return symbols


def extract_text_window(
    object_path: str | Path, *, function: str | None
) -> ObjectWindow:
    """Return the compared window: whole ``.text``, or one symbol's range."""

    path = Path(object_path)
    try:
        data = path.read_bytes()
    except OSError as error:
        raise LineProbeError(
            f"could not read compiled object {path}: {error}"
        ) from error
    try:
        endian, is64, sections = _parse_elf_sections(data)
    except ElfFormatError as error:
        raise ElfFormatError(f"{path}: {error}") from error
    by_name = {section.name: section for section in sections if section.name}
    text = by_name.get(".text")
    if text is None:
        available = ", ".join(sorted(by_name)) or "none"
        raise ElfFormatError(
            f"{path}: object has no .text section (sections present: {available})"
        )
    text_bytes = data[text.offset : text.offset + text.size]
    if function is None:
        return ObjectWindow(
            words=_chunk_words(text_bytes),
            source=f".text (whole section, {len(text_bytes)} byte(s))",
            byte_length=len(text_bytes),
        )
    symtab = by_name.get(".symtab")
    if symtab is None:
        raise ElfFormatError(
            f"{path}: object has no .symtab section, so --function {function!r} "
            "cannot be windowed. Omit --function for whole-.text mode: IDO "
            "commonly strips, or never emits, symbol-table entries for "
            "static functions."
        )
    symbols = _parse_symbols(
        data, endian=endian, is64=is64, symtab=symtab, sections=sections
    )
    matches = [item for item in symbols if item.name == function]
    if not matches:
        names = sorted(
            {item.name for item in symbols if item.name and item.kind == STT_FUNC}
        )
        shown = ", ".join(names[:20]) + (", ..." if len(names) > 20 else "")
        listing = f" (function symbols present: {shown})" if shown else ""
        raise ElfFormatError(
            f"{path}: no symbol named {function!r} in the object's symbol "
            f"table{listing}. Omit --function for whole-.text mode: IDO "
            "commonly strips, or never emits, symbol-table entries for "
            "static functions."
        )
    symbol = matches[0]
    if symbol.shndx != text.index:
        raise ElfFormatError(
            f"{path}: symbol {function!r} is not defined in .text (its "
            f"section index is {symbol.shndx}); pass a function known to be "
            "in .text, or omit --function for whole-.text mode"
        )
    if symbol.size == 0:
        raise ElfFormatError(
            f"{path}: symbol {function!r} has size 0 in the symbol table (no "
            "ELF size recorded - common for assembly-defined or "
            "size-stripped symbols). Omit --function for whole-.text mode."
        )
    start = symbol.value - text.addr
    end = start + symbol.size
    if start < 0 or end > len(text_bytes):
        raise ElfFormatError(
            f"{path}: symbol {function!r} (value=0x{symbol.value:x} "
            f"size={symbol.size}) falls outside the .text section's bounds; "
            "the object may not match the compile command that produced it"
        )
    window_bytes = text_bytes[start:end]
    return ObjectWindow(
        words=_chunk_words(window_bytes),
        source=f".text[{function}] ({symbol.size} byte(s) at +0x{start:x})",
        byte_length=len(window_bytes),
    )


# ---------------------------------------------------------------------------
# Word-level scoring
# ---------------------------------------------------------------------------


def word_diff_positions(left: tuple[bytes, ...], right: tuple[bytes, ...]) -> int:
    """Count positions (including any length difference) that differ."""

    return sum(
        1 for a, b in itertools.zip_longest(left, right, fillvalue=None) if a != b
    )


def score_against_target(
    variant_words: tuple[bytes, ...],
    baseline_words: tuple[bytes, ...],
    target_words: tuple[bytes, ...],
) -> dict[str, int]:
    """Return the toward/away/unchanged partition against a target window.

    This is the campaign's emotionally important number: of the sites where
    baseline already disagreed with the target, how many did this variant
    fix (``toward``), how many newly-agreeing sites did it break
    (``away``), and how many sites kept whatever agreement state they had
    (``unchanged``)? The three always sum to `total_positions`.
    """

    total = max(len(variant_words), len(baseline_words), len(target_words))
    baseline_mismatch = {
        index
        for index, (word, expected) in enumerate(
            itertools.zip_longest(baseline_words, target_words, fillvalue=None)
        )
        if word != expected
    }
    variant_mismatch = {
        index
        for index, (word, expected) in enumerate(
            itertools.zip_longest(variant_words, target_words, fillvalue=None)
        )
        if word != expected
    }
    toward = len(baseline_mismatch - variant_mismatch)
    away = len(variant_mismatch - baseline_mismatch)
    return {
        "toward": toward,
        "away": away,
        "unchanged": total - toward - away,
        "total_positions": total,
        "mismatched_vs_target": len(variant_mismatch),
    }


def _load_target_words(
    *,
    target_bytes: str | Path | None,
    target_offset: int,
    target_object: str | Path | None,
    function: str | None,
) -> tuple[bytes, ...]:
    if target_bytes is not None:
        path = Path(target_bytes).expanduser().resolve()
        if not path.is_file():
            raise FileNotFoundError(f"--target-bytes does not exist: {path}")
        data = path.read_bytes()
        if target_offset < 0 or target_offset > len(data):
            raise LineProbeError(
                f"--target-offset {target_offset} is out of range for {path} "
                f"({len(data)} byte(s))"
            )
        return _chunk_words(data[target_offset:])
    path = Path(target_object).expanduser().resolve()  # type: ignore[arg-type]
    if not path.is_file():
        raise FileNotFoundError(f"--target-object does not exist: {path}")
    return extract_text_window(path, function=function).words


# ---------------------------------------------------------------------------
# Verdict
# ---------------------------------------------------------------------------

VERDICT_LINE_SENSITIVE = "line-sensitive"
VERDICT_NOT_LINE_SENSITIVE = "not-line-sensitive"
VERDICT_NONDETERMINISTIC = "nondeterministic"


def classify_verdict(
    split_diff: int, shift_diff: int, *, shift_lines: int
) -> tuple[str, str]:
    """Return the verdict name and its human-readable message.

    The three outcomes here are exhaustive and mutually exclusive: a
    nondeterministic control result is reported before either the
    line-sensitivity question is asked, because a control failure means
    every other number from this probe is unearned.
    """

    if shift_diff:
        return (
            VERDICT_NONDETERMINISTIC,
            "NONDETERMINISTIC COMPILE: global-shift "
            f"({shift_lines} blank line(s) prepended - a pure line-number "
            "relabeling with no statement regrouping) must never change the "
            f"compiled object, but {shift_diff} word(s) differ from "
            "baseline. Every other verdict from this probe is untrustworthy "
            "until the compile command is made deterministic under trivial "
            "padding (check embedded timestamps, random seeds, "
            "uninitialized padding bytes, or absolute paths/line numbers "
            "baked into the object).",
        )
    if split_diff:
        return (
            VERDICT_LINE_SENSITIVE,
            "LINE-SENSITIVE: statement line assignment participates in "
            "scheduling. next: field-guide lever 23 (preprocessor line "
            "assignment) — try acpp preprocessing: "
            "acpp <defines> file.c > file.i && cc -c <flags> file.i",
        )
    return (
        VERDICT_NOT_LINE_SENSITIVE,
        "NOT line-sensitive under this reflow; the schedule residue is "
        "owned elsewhere (compiler binary, flags, or instruction "
        "selection).",
    )


def next_steps(
    verdict: str,
    *,
    ties: Sequence[tuple[int, int]] = (),
    target: dict[str, dict[str, int]] | None = None,
) -> tuple[str, ...]:
    """Return the routing lines a verdict owes its reader.

    The verdict names a mechanism; these name the next command. A probe that
    proves line assignment owns the residue and then stops has answered the
    question the reader asked and none of the question they have next, which
    is *which* line each statement needs - and that is exactly what `--tie`
    measures.
    """

    if verdict == VERDICT_NONDETERMINISTIC:
        # Nothing downstream is earned until the control passes; routing a
        # reader onward here would be routing them onto untrustworthy numbers.
        return ()
    if verdict == VERDICT_NOT_LINE_SENSITIVE:
        return (
            "this rules preprocessor line assignment out for this input only; "
            "stay on the compiler/flags branch: decomp-workbench guide "
            "g0-schedule-probe",
        )
    if not ties:
        steps = [
            "retarget one statement: re-run with --tie STATEMENT=LINE (e.g. "
            "--tie 83=88, repeatable) to compile a token-identical fourth "
            "variant that gives just that statement the line number you think "
            "it needs - usually its target-order neighbor's."
        ]
        if target is None:
            # Only worth saying to a reader who has not already scored this
            # run; telling them to pass a flag they passed is noise.
            steps.append(
                "add --target-object/--target-bytes so the tie is scored "
                "toward and away from the target; a word diff against "
                "baseline says it moved, not that it moved the right way."
            )
        return tuple(steps)
    score = (target or {}).get("tie")
    if score is None:
        return (
            "the tie compiled, but nothing scored it: add --target-object or "
            "--target-bytes to see whether it moved toward the target.",
        )
    toward, away = score["toward"], score["away"]
    if toward > away:
        return (
            f"the tie moved {toward} site(s) toward the target and {away} "
            "away: line assignment owns those statements. Now hunt the "
            "natural spelling that carries the same assignment - "
            "decomp-workbench guide 25 (logical-line splices) - because a "
            "#line pair is a probe, not a publishable decompilation.",
        )
    return (
        f"the tie moved {toward} site(s) toward the target and {away} away: "
        "this assignment is not the one. Try another line for the same "
        "statement, or another statement; the plateau you measure is scoped "
        "to the statement order you swept.",
    )


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------


def _variant_payload(compiled: VariantCompile, window: ObjectWindow) -> dict[str, Any]:
    return {
        "name": compiled.name,
        "description": VARIANT_DESCRIPTIONS[compiled.name],
        "command": compiled.command,
        "source_path": compiled.source_path,
        "object_path": compiled.object_path,
        "returncode": compiled.returncode,
        "duration_seconds": compiled.duration_seconds,
        "window": window.source,
        "word_count": len(window.words),
        "stdout_path": compiled.stdout_path,
        "stderr_path": compiled.stderr_path,
        "stdout": compiled.stdout_preview,
        "stderr": compiled.stderr_preview,
    }


def run_line_probe(
    input_path: str | Path,
    *,
    compile_template: str,
    function: str | None = None,
    split_threshold: int = DEFAULT_SPLIT_THRESHOLD,
    shift_lines: int = DEFAULT_SHIFT_LINES,
    work_dir: str | Path = DEFAULT_WORK_DIR,
    compile_cwd: str | Path | None = None,
    environment: dict[str, str] | None = None,
    timeout: float = 120.0,
    stream_limit: int = DEFAULT_STREAM_LIMIT,
    artifact_dir: str | Path | None = None,
    target_bytes: str | Path | None = None,
    target_offset: int = 0,
    target_object: str | Path | None = None,
    ties: Sequence[tuple[int, int]] | None = None,
) -> dict[str, Any]:
    """Compile the deterministic variants and report the verdict."""

    if target_bytes is not None and target_object is not None:
        raise LineProbeError(
            "--target-bytes and --target-object are mutually exclusive"
        )
    if target_offset and target_bytes is None:
        raise LineProbeError("--target-offset requires --target-bytes")
    if timeout <= 0:
        raise LineProbeError("--timeout must be positive")

    source = Path(input_path).expanduser().resolve()
    if not source.is_file():
        raise FileNotFoundError(
            f"preprocessed input does not exist: {source}; expected "
            f"{PREPROCESSED_INPUT_HELP}"
        )
    text = source.read_text(encoding="utf-8")

    cwd = (
        Path(compile_cwd).expanduser().resolve()
        if compile_cwd
        else Path.cwd().resolve()
    )
    if not cwd.is_dir():
        raise NotADirectoryError(f"compile working directory does not exist: {cwd}")

    root = Path(work_dir).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    run_dir = Path(tempfile.mkdtemp(prefix="probe-lines-", dir=root))

    variant_sources = generate_variants(
        text, split_threshold=split_threshold, shift_lines=shift_lines, ties=ties
    )
    active_names = tuple(variant_sources)

    compiled: dict[str, VariantCompile] = {}
    for name in active_names:
        result = compile_variant(
            name,
            variant_sources[name],
            run_dir=run_dir,
            compile_template=compile_template,
            compile_cwd=cwd,
            environment=environment or {},
            timeout=timeout,
            stream_limit=stream_limit,
            artifact_dir=artifact_dir,
        )
        compiled[name] = result
        if not result.compiled:
            detail_lines = result.stderr_preview.strip().splitlines()
            detail = detail_lines[-1] if detail_lines else "no diagnostic"
            raise RuntimeError(
                f"{name} variant failed to compile (exit {result.returncode}): "
                f"{detail}\n"
                f"full stderr: {result.stderr_path}\n"
                f"run directory (not cleaned up): {run_dir}"
            )

    windows: dict[str, ObjectWindow] = {}
    for name, result in compiled.items():
        assert result.object_path is not None  # guaranteed by the guard above
        try:
            windows[name] = extract_text_window(result.object_path, function=function)
        except ElfFormatError as error:
            raise ElfFormatError(
                f"{name} variant: {error}\nrun directory (not cleaned up): {run_dir}"
            ) from error

    baseline_words = windows["baseline"].words
    split_words = windows["split-statements"].words
    shift_words = windows["global-shift"].words

    split_diff = word_diff_positions(baseline_words, split_words)
    shift_diff = word_diff_positions(baseline_words, shift_words)
    tie_diff = (
        word_diff_positions(baseline_words, windows["tie"].words)
        if "tie" in windows
        else None
    )
    verdict, message = classify_verdict(split_diff, shift_diff, shift_lines=shift_lines)

    target_report: dict[str, dict[str, int]] | None = None
    if target_bytes is not None or target_object is not None:
        target_words = _load_target_words(
            target_bytes=target_bytes,
            target_offset=target_offset,
            target_object=target_object,
            function=function,
        )
        target_report = {
            name: score_against_target(
                windows[name].words, baseline_words, target_words
            )
            for name in active_names
        }

    variant_payloads = {
        name: _variant_payload(compiled[name], windows[name]) for name in active_names
    }
    return {
        "schema": LINE_PROBE_SCHEMA,
        "input": display_path(source),
        "function": function,
        "split_threshold": split_threshold,
        "shift_lines": shift_lines,
        # The ties are part of the experiment's definition, exactly as
        # `split_threshold` and `shift_lines` are: a report that cannot say
        # which statements it retargeted cannot be re-run from its own record.
        "ties": [[statement, assigned] for statement, assigned in (ties or ())],
        "run_directory": str(run_dir),
        "variants": variant_payloads,
        "split_word_diff": split_diff,
        "shift_word_diff": shift_diff,
        "tie_word_diff": tie_diff,
        "verdict": verdict,
        "message": message,
        "next_steps": list(next_steps(verdict, ties=ties or (), target=target_report)),
        "target": target_report,
    }
