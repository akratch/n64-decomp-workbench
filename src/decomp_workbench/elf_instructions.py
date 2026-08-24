"""Read a true per-object instruction count directly from ELF section bytes.

``.text`` is padded to a 16-byte (4-instruction) boundary by the linker, so a
count derived from section size -- or from any disassembly that was never
trimmed of that padding -- over-reports the real body of a function whose
length is not itself a multiple of four instructions. A probe that is three
instructions *longer* than the target can therefore report the same
"4644/4644" count as a probe that matches exactly, because the padding on the
shorter function absorbs the difference. One campaign's gate passed such a
probe; every stage after it had to re-derive the true count by hand with::

    mips-linux-gnu-objdump -d obj.o | grep -c '^ *[0-9a-f]*:'

That command works only because GNU objdump's *default* mode (no ``-z``)
elides runs of zero bytes instead of printing them, so the padding never
reaches the ``grep -c`` count. This module gets the same number without
invoking objdump at all, or relying on which flags a caller happened to pass:
it reads the section's raw bytes from the ELF file and applies the one rule
that actually defines "padding" here -- trailing all-zero words after the
delay slot that follows the function's final ``jr $ra`` are unreachable
alignment filler, not code. That is the same rule
:func:`decomp_workbench.objdump.trim_function_padding` applies to already
disassembled text; this module applies it natively, straight from the
object, so the count does not depend on how (or whether) a symbol was
disassembled.

This intentionally answers the same question the hand command does: the
*whole* section's real instruction count. It does not attempt to bound a
single symbol inside a multi-function section -- these objects commonly carry
no ELF size for their functions at all (see `trim_function_padding`'s own
docstring), so there is nothing more precise to read. Callers comparing one
named symbol out of several should treat this as "how long is the section",
not "how long is the symbol", and fall back to the disassembly-based count
for that question.

This module reads ELF32 big-endian bytes with its own minimal struct code, and
so do :mod:`decomp_workbench.elf_symbols`, :mod:`decomp_workbench.ldmap`,
:mod:`decomp_workbench.line_probe`, :mod:`decomp_workbench.objdump`. Each
answers one narrow question and each declines rather than raising where a
general reader would refuse the file. :mod:`decomp_workbench.elf` is the
intended future home for all of them; folding them in changes five distinct
failure behaviours, so it is deliberate work rather than a refactor to do in
passing.
"""

from __future__ import annotations

import struct
from pathlib import Path

#: MIPS `jr $ra`: opcode SPECIAL (0), rs=$ra (31), rt=0, rd=0, shamt=0,
#: funct=JR (0x08). A function's ABI epilogue owns exactly one delay-slot
#: instruction after this word; anything past that, if it is all zero, is
#: alignment padding rather than emitted code.
JR_RA_WORD = 0x03E00008

#: ELF32 identification bytes this module understands. N64/MIPS o32 objects
#: are always big-endian 32-bit ELF; anything else is a format this reader
#: was not written for, and it says so rather than mis-measuring silently.
_ELF_MAGIC = b"\x7fELF"
_ELFCLASS32 = 1
_ELFDATA2MSB = 2


class ElfFormatError(ValueError):
    """The file is not a supported ELF32 big-endian relocatable object."""


def _section_bytes(data: bytes, section: str) -> bytes | None:
    """Return one section's raw content, or ``None`` when it is absent.

    Raises :class:`ElfFormatError` for anything that is not a big-endian
    32-bit ELF file -- the one format this reader was written against -- so a
    caller can tell "not a MIPS object" from "no such section".
    """

    if len(data) < 52 or data[:4] != _ELF_MAGIC:
        raise ElfFormatError("not an ELF file (bad magic)")
    ei_class = data[4]
    ei_data = data[5]
    if ei_class != _ELFCLASS32:
        raise ElfFormatError(
            f"only 32-bit ELF (EI_CLASS=1) is supported, got class {ei_class}"
        )
    if ei_data != _ELFDATA2MSB:
        raise ElfFormatError(
            f"only big-endian ELF (EI_DATA=2) is supported, got data encoding {ei_data}"
        )

    endian = ">"
    (e_shoff,) = struct.unpack_from(endian + "I", data, 0x20)
    (e_shentsize,) = struct.unpack_from(endian + "H", data, 0x2E)
    (e_shnum,) = struct.unpack_from(endian + "H", data, 0x30)
    (e_shstrndx,) = struct.unpack_from(endian + "H", data, 0x32)
    if e_shoff == 0 or e_shnum == 0:
        raise ElfFormatError("ELF file carries no section header table")

    def header(index: int) -> tuple[int, int, int, int]:
        offset = e_shoff + index * e_shentsize
        name_off, sh_type, _flags, _addr, sh_offset, sh_size = struct.unpack_from(
            endian + "6I", data, offset
        )
        return name_off, sh_type, sh_offset, sh_size

    _name_off, _type, str_offset, str_size = header(e_shstrndx)
    shstrtab = data[str_offset : str_offset + str_size]

    def name_at(offset: int) -> str:
        end = shstrtab.index(b"\x00", offset)
        return shstrtab[offset:end].decode("ascii", errors="replace")

    SHT_NOBITS = 8
    for index in range(e_shnum):
        name_off, sh_type, sh_offset, sh_size = header(index)
        if name_at(name_off) != section:
            continue
        if sh_type == SHT_NOBITS:
            return b""
        return data[sh_offset : sh_offset + sh_size]
    return None


def read_section(path: str | Path, section: str = ".text") -> bytes | None:
    """Return one ELF section's raw bytes, or ``None`` when it is absent."""

    return _section_bytes(Path(path).read_bytes(), section)


#: The minimum trailing all-zero run GNU objdump's default (non-``-z``) mode
#: actually elides, in words. Measured, not assumed: a single trailing zero
#: word is printed as a real ``nop`` instruction (confirmed both against a
#: hand-assembled fixture and against a real campaign object whose function
#: ends in a genuine single-word `nop` with no alignment padding after it --
#: `.text` was already a multiple of 4 words long, so nothing followed it),
#: while a run of two or more is elided as ``...``. Trimming on a shorter run
#: over-counts padding and drops one real instruction from the count; this
#: cost exactly that word on one campaign object before it was measured.
MINIMUM_ELIDED_RUN = 2


def true_instruction_count_from_bytes(raw: bytes) -> int:
    """Count real instructions in raw section bytes, trimming trailing padding.

    Finds the *last* ``jr $ra`` word in the section, keeps its delay slot, and
    drops everything after it only when every word past the delay slot is
    zero *and* there are at least :data:`MINIMUM_ELIDED_RUN` of them -- the
    same threshold GNU objdump's default disassembly applies before it elides
    a run of zero bytes as ``...`` instead of printing them. A section with no
    ``jr $ra`` at all, non-zero content after the last one (a multi-function
    section whose final function does not end in a plain return), or exactly
    one trailing zero word (a real trailing ``nop`` objdump would still
    print), is reported at its full word count -- there is nothing safe to
    trim.
    """

    word_count = len(raw) // 4
    words = struct.unpack(f">{word_count}I", raw[: word_count * 4])
    last_return = None
    for index, word in enumerate(words):
        if word == JR_RA_WORD:
            last_return = index
    if last_return is None or last_return + 2 >= word_count:
        return word_count
    trailing = words[last_return + 2 :]
    if len(trailing) >= MINIMUM_ELIDED_RUN and all(word == 0 for word in trailing):
        return last_return + 2
    return word_count


def true_instruction_count(path: str | Path, *, section: str = ".text") -> int | None:
    """Return the real (unpadded) instruction count of ``section`` in ``path``.

    ``None`` when the section is absent or empty -- there is nothing to
    count, which is different from counting zero real instructions in a
    section that exists.
    """

    raw = read_section(path, section)
    if not raw:
        return None
    return true_instruction_count_from_bytes(raw)
