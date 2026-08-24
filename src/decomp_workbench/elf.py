"""A generic ELF32 big-endian reader: sections, symbols, and relocations.

:mod:`decomp_workbench.elf_instructions` already reads one section's raw
bytes for the padding-safe instruction count, and :mod:`decomp_workbench.
objdump` reads instructions and relocations from *disassembly text* because
that is what the comparison core needs. Neither exposes the symbol table or
a relocation's numeric type and symbol index -- the two facts a *static*
object audit needs and objdump's `-r` text only half-prints (it names the
symbol, never whether that symbol is itself defined in this object).

This module is the third leg: every section header field, the full symbol
table (name, value, size, bind/type, section index), and every relocation
entry (offset, symbol index, numeric type) resolved back to the section it
applies to. It is deliberately permissive at this layer -- a missing
`.symtab` or a relocation section whose declared `sh_entsize` disagrees with
what `Elf32_Rel` actually is are facts a caller like
:mod:`decomp_workbench.target_audit` reports as findings, not failures this
reader refuses to parse past. The one thing it does refuse is a file that is
not a 32-bit big-endian ELF at all -- there is nothing here to read from
that at any layer.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass
from pathlib import Path

__all__ = [
    "ELF32_REL_ENTSIZE",
    "ELF32_SYM_ENTSIZE",
    "R_MIPS_NAMES",
    "SHN_ABS",
    "SHN_COMMON",
    "SHN_UNDEF",
    "SHT_NOBITS",
    "SHT_NULL",
    "SHT_PROGBITS",
    "SHT_REL",
    "SHT_STRTAB",
    "SHT_SYMTAB",
    "ElfFormatError",
    "ElfObject",
    "Reloc",
    "Section",
    "Symbol",
    "parse_elf",
    "r_mips_name",
    "read_elf",
]

_ELF_MAGIC = b"\x7fELF"
_ELFCLASS32 = 1
_ELFDATA2MSB = 2

SHT_NULL = 0
SHT_PROGBITS = 1
SHT_SYMTAB = 2
SHT_STRTAB = 3
SHT_REL = 9
SHT_NOBITS = 8

SHN_UNDEF = 0
SHN_ABS = 0xFFF1
SHN_COMMON = 0xFFF2

#: The size a conforming `Elf32_Rel` and `Elf32_Sym` entry actually is. A
#: section's own `sh_entsize` is read and compared against these, never
#: assumed -- see `target_audit`'s `reloc-entsize-mismatch` finding.
ELF32_REL_ENTSIZE = 8
ELF32_SYM_ENTSIZE = 16

#: MIPS relocation type numbers this module knows the name of. An unknown
#: number is still reported (as ``R_MIPS_<n>``, see `r_mips_name`) rather
#: than dropped -- the campaign that motivated this module cost a target
#: five phantom points to a relocation nobody looked at closely enough.
R_MIPS_NAMES: dict[int, str] = {
    0: "R_MIPS_NONE",
    1: "R_MIPS_16",
    2: "R_MIPS_32",
    3: "R_MIPS_REL32",
    4: "R_MIPS_26",
    5: "R_MIPS_HI16",
    6: "R_MIPS_LO16",
    7: "R_MIPS_GPREL16",
    8: "R_MIPS_LITERAL",
    9: "R_MIPS_GOT16",
    10: "R_MIPS_PC16",
    11: "R_MIPS_CALL16",
    12: "R_MIPS_GPREL32",
    16: "R_MIPS_SHIFT5",
    17: "R_MIPS_SHIFT6",
    18: "R_MIPS_64",
    19: "R_MIPS_GOT_DISP",
    20: "R_MIPS_GOT_PAGE",
    21: "R_MIPS_GOT_OFST",
    22: "R_MIPS_GOT_HI16",
    23: "R_MIPS_GOT_LO16",
    24: "R_MIPS_SUB",
    30: "R_MIPS_JALR",
}


def r_mips_name(r_type: int) -> str:
    """Return the MIPS relocation name for ``r_type``, numeric if unknown."""

    return R_MIPS_NAMES.get(r_type, f"R_MIPS_{r_type}")


class ElfFormatError(ValueError):
    """The file is not a supported ELF32 big-endian relocatable object."""


@dataclass(frozen=True)
class Section:
    """One ELF section header, every field this reader parses."""

    index: int
    name: str
    type: int
    flags: int
    addr: int
    offset: int
    size: int
    link: int
    info: int
    addralign: int
    entsize: int

    def as_dict(self) -> dict[str, object]:
        return {
            "index": self.index,
            "name": self.name,
            "type": self.type,
            "flags": self.flags,
            "addr": self.addr,
            "offset": self.offset,
            "size": self.size,
            "link": self.link,
            "info": self.info,
            "addralign": self.addralign,
            "entsize": self.entsize,
        }


@dataclass(frozen=True)
class Symbol:
    """One `.symtab` entry."""

    index: int
    name: str
    value: int
    size: int
    info: int
    other: int
    shndx: int

    @property
    def bind(self) -> int:
        return self.info >> 4

    @property
    def type(self) -> int:
        return self.info & 0xF

    @property
    def defined(self) -> bool:
        """Whether this symbol resolves inside *this* object.

        `SHN_UNDEF` is the one shape that matters to the literal-pool
        heuristic: a symbol an object's own `.text` relocates against but
        never defines is either a real external (a genuine `extern`) or, in
        the motivating case, a datum that belongs to this object and was
        extracted somewhere else. `SHN_ABS`/`SHN_COMMON` are defined in the
        sense this property means -- the object carries a real answer for
        them, just not a section-relative one.
        """

        return self.shndx != SHN_UNDEF

    def as_dict(self) -> dict[str, object]:
        return {
            "index": self.index,
            "name": self.name,
            "value": self.value,
            "size": self.size,
            "bind": self.bind,
            "type": self.type,
            "shndx": self.shndx,
            "defined": self.defined,
        }


@dataclass(frozen=True)
class Reloc:
    """One `Elf32_Rel` entry, resolved back to the section it applies to."""

    offset: int
    sym_index: int
    type: int
    applies_to: str

    @property
    def kind(self) -> str:
        return r_mips_name(self.type)

    def as_dict(self) -> dict[str, object]:
        return {
            "offset": self.offset,
            "sym_index": self.sym_index,
            "type": self.type,
            "kind": self.kind,
            "applies_to": self.applies_to,
        }


@dataclass(frozen=True)
class ElfObject:
    """A parsed ELF32 big-endian relocatable object."""

    path: str | None
    data: bytes
    sections: tuple[Section, ...]
    symbols: tuple[Symbol, ...]
    #: Relocations keyed by the section name they apply to (``.text``,
    #: ``.rodata``, ...), in file order.
    relocations: dict[str, tuple[Reloc, ...]]
    #: Sections declared `SHT_REL` whose own header this reader could not
    #: fully trust (bad `sh_link`/`sh_info`, or an entry count implied by
    #: `sh_size` that does not divide evenly). Each is a section name; the
    #: relocations dict still carries whatever the fallback (declared
    #: `ELF32_REL_ENTSIZE`) could read for it, unindexed by sh_info if that
    #: was the very thing that was wrong.
    malformed_reloc_sections: tuple[str, ...] = ()

    def section(self, name: str) -> Section | None:
        for item in self.sections:
            if item.name == name:
                return item
        return None

    def section_bytes(self, name: str) -> bytes | None:
        section = self.section(name)
        if section is None:
            return None
        if section.type == SHT_NOBITS:
            return b""
        return self.data[section.offset : section.offset + section.size]

    def symbol(self, index: int) -> Symbol | None:
        if 0 <= index < len(self.symbols):
            return self.symbols[index]
        return None

    def relocations_for(self, name: str) -> tuple[Reloc, ...]:
        return self.relocations.get(name, ())

    def symbol_name(self, index: int) -> str | None:
        found = self.symbol(index)
        return found.name if found is not None else None


def _string(strtab: bytes, offset: int) -> str:
    if offset < 0 or offset > len(strtab):
        return ""
    end = strtab.find(b"\x00", offset)
    if end == -1:
        end = len(strtab)
    return strtab[offset:end].decode("ascii", errors="replace")


def parse_elf(data: bytes, *, path: str | None = None) -> ElfObject:
    """Parse an ELF32 big-endian relocatable object from raw bytes.

    Raises :class:`ElfFormatError` only for what makes the file unreadable
    as this format at all (bad magic, wrong class/endianness, no section
    header table). Everything an ELF *could* get wrong past that point --
    entry-size mismatches, a relocation section pointing at a `sh_link` that
    is not a symbol table, a symbol index a relocation names that does not
    exist -- is a fact this reader hands back rather than an exception it
    raises, because those facts are exactly what a target audit reports as
    findings.
    """

    if len(data) < 52 or data[:4] != _ELF_MAGIC:
        raise ElfFormatError("not an ELF file (bad magic)")
    if data[4] != _ELFCLASS32:
        raise ElfFormatError(
            f"only 32-bit ELF (EI_CLASS=1) is supported, got {data[4]}"
        )
    if data[5] != _ELFDATA2MSB:
        raise ElfFormatError(
            f"only big-endian ELF (EI_DATA=2) is supported, got {data[5]}"
        )

    endian = ">"
    (e_shoff,) = struct.unpack_from(endian + "I", data, 0x20)
    (e_shentsize,) = struct.unpack_from(endian + "H", data, 0x2E)
    (e_shnum,) = struct.unpack_from(endian + "H", data, 0x30)
    (e_shstrndx,) = struct.unpack_from(endian + "H", data, 0x32)
    if e_shoff == 0 or e_shnum == 0:
        raise ElfFormatError("ELF file carries no section header table")

    def raw_header(
        index: int,
    ) -> tuple[int, int, int, int, int, int, int, int, int, int]:
        offset = e_shoff + index * e_shentsize
        return struct.unpack_from(endian + "10I", data, offset)

    if not (0 <= e_shstrndx < e_shnum):
        raise ElfFormatError(f"e_shstrndx {e_shstrndx} names no section")
    _, _, _, _, shstr_offset, shstr_size, *_ = raw_header(e_shstrndx)
    shstrtab = data[shstr_offset : shstr_offset + shstr_size]

    sections: list[Section] = []
    for index in range(e_shnum):
        name_off, sh_type, flags, addr, offset, size, link, info, align, entsize = (
            raw_header(index)
        )
        sections.append(
            Section(
                index=index,
                name=_string(shstrtab, name_off),
                type=sh_type,
                flags=flags,
                addr=addr,
                offset=offset,
                size=size,
                link=link,
                info=info,
                addralign=align,
                entsize=entsize,
            )
        )

    symbols: list[Symbol] = []
    symtab = next((item for item in sections if item.type == SHT_SYMTAB), None)
    if symtab is not None:
        strtab_section = (
            sections[symtab.link] if 0 <= symtab.link < len(sections) else None
        )
        strtab = (
            data[strtab_section.offset : strtab_section.offset + strtab_section.size]
            if strtab_section is not None
            else b""
        )
        raw = data[symtab.offset : symtab.offset + symtab.size]
        count = len(raw) // ELF32_SYM_ENTSIZE
        for index in range(count):
            entry_offset = index * ELF32_SYM_ENTSIZE
            st_name, st_value, st_size, st_info, st_other, st_shndx = (
                struct.unpack_from(endian + "IIIBBH", raw, entry_offset)
            )
            symbols.append(
                Symbol(
                    index=index,
                    name=_string(strtab, st_name),
                    value=st_value,
                    size=st_size,
                    info=st_info,
                    other=st_other,
                    shndx=st_shndx,
                )
            )

    relocations: dict[str, list[Reloc]] = {}
    malformed: list[str] = []
    for section in sections:
        if section.type != SHT_REL:
            continue
        target = sections[section.info] if 0 <= section.info < len(sections) else None
        target_name = target.name if target is not None else section.name
        entsize = section.entsize or ELF32_REL_ENTSIZE
        raw = data[section.offset : section.offset + section.size]
        malformed_here = (
            target is None
            or entsize != ELF32_REL_ENTSIZE
            or section.size % ELF32_REL_ENTSIZE != 0
            or not (0 <= section.link < len(sections))
            or sections[section.link].type != SHT_SYMTAB
        )
        if malformed_here:
            malformed.append(section.name)
        # Read with the *correct* Elf32_Rel width regardless of what the
        # header declared, so a target audit still sees the entries a
        # mis-declared entsize would otherwise hide entirely.
        count = len(raw) // ELF32_REL_ENTSIZE
        entries: list[Reloc] = []
        for index in range(count):
            r_offset, r_info = struct.unpack_from(
                endian + "II", raw, index * ELF32_REL_ENTSIZE
            )
            entries.append(
                Reloc(
                    offset=r_offset,
                    sym_index=r_info >> 8,
                    type=r_info & 0xFF,
                    applies_to=target_name,
                )
            )
        relocations.setdefault(target_name, []).extend(entries)

    return ElfObject(
        path=path,
        data=data,
        sections=tuple(sections),
        symbols=tuple(symbols),
        relocations={name: tuple(items) for name, items in relocations.items()},
        malformed_reloc_sections=tuple(malformed),
    )


def read_elf(path: str | Path) -> ElfObject:
    """Parse an ELF32 big-endian relocatable object from a file path."""

    resolved = Path(path)
    return parse_elf(resolved.read_bytes(), path=str(resolved))
