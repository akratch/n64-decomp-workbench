"""A minimal ELF32 big-endian object builder for ELF-reading test fixtures.

Deliberately hand-rolled rather than shelling out to a real assembler: the
workbench's own test suite must not depend on a MIPS toolchain being
installed, and the byte layout this module writes is simple enough (one
NULL section, the caller's sections, one `.shstrtab`) to encode directly and
keep honest.
"""

from __future__ import annotations

import struct
from collections.abc import Sequence
from dataclasses import dataclass

ELF_HEADER_SIZE = 52
SECTION_HEADER_SIZE = 40


def build_elf32be(sections: dict[str, bytes]) -> bytes:
    """Return a minimal valid ELF32 big-endian relocatable object.

    ``sections`` maps section name to raw content; every section is emitted
    as ``SHT_PROGBITS``. A ``.shstrtab`` is generated and appended
    automatically, so callers only supply the sections they want to assert
    against.
    """

    names = ["", *sections.keys(), ".shstrtab"]
    shstrtab = b"\x00".join(name.encode("ascii") for name in names) + b"\x00"
    name_offsets: dict[str, int] = {}
    cursor = 0
    for name in names:
        name_offsets[name] = cursor
        cursor += len(name.encode("ascii")) + 1

    body_offset = ELF_HEADER_SIZE
    section_bodies: list[tuple[str, bytes, int]] = []
    offset = body_offset
    for name, content in sections.items():
        section_bodies.append((name, content, offset))
        offset += len(content)
    shstrtab_offset = offset
    offset += len(shstrtab)
    shoff = offset

    header_count = 1 + len(sections) + 1  # NULL + caller sections + shstrtab
    shstrndx = header_count - 1

    elf_header = struct.pack(
        ">16sHHIIIIIHHHHHH",
        b"\x7fELF\x01\x02\x01" + b"\x00" * 9,
        1,  # e_type: ET_REL
        8,  # e_machine: EM_MIPS
        1,  # e_version
        0,  # e_entry
        0,  # e_phoff
        shoff,  # e_shoff
        0,  # e_flags
        ELF_HEADER_SIZE,  # e_ehsize
        0,  # e_phentsize
        0,  # e_phnum
        SECTION_HEADER_SIZE,  # e_shentsize
        header_count,  # e_shnum
        shstrndx,  # e_shstrndx
    )

    def section_header(
        name_off: int, sh_type: int, sh_offset: int, sh_size: int
    ) -> bytes:
        return struct.pack(
            ">10I", name_off, sh_type, 0, 0, sh_offset, sh_size, 0, 0, 0, 0
        )

    SHT_NULL = 0
    SHT_PROGBITS = 1
    SHT_STRTAB = 3
    headers = [section_header(0, SHT_NULL, 0, 0)]
    for name, content, section_offset in section_bodies:
        headers.append(
            section_header(
                name_offsets[name], SHT_PROGBITS, section_offset, len(content)
            )
        )
    headers.append(
        section_header(
            name_offsets[".shstrtab"], SHT_STRTAB, shstrtab_offset, len(shstrtab)
        )
    )

    return (
        elf_header
        + b"".join(content for _name, content, _offset in section_bodies)
        + shstrtab
        + b"".join(headers)
    )


def words(*values: int) -> bytes:
    """Pack big-endian 32-bit words, the way `.text` bytes are laid out."""

    return b"".join(struct.pack(">I", value) for value in values)


#: Symbol types, spelled out because the difference between them is the whole
#: point of the fixtures that use this module's symbol-table support: a jump
#: table destination inside a function body is ``STT_NOTYPE``, and a function
#: entry is ``STT_FUNC``. A reader who cannot tell them apart carves a
#: function's prologue out of its body. See `decomp_workbench.elf_symbols`.
STT_NOTYPE = 0
STT_FUNC = 2

STB_LOCAL = 0
STB_GLOBAL = 1


def build_object(
    *,
    text: bytes,
    symbols: list[tuple[str, int, int, int, int]],
    section: str = ".text",
) -> bytes:
    """Return an ELF32 big-endian object with one code section and a symtab.

    ``symbols`` is a list of ``(name, value, size, kind, binding)``, where
    ``kind`` is ``STT_FUNC``/``STT_NOTYPE`` and ``binding`` is
    ``STB_LOCAL``/``STB_GLOBAL``. Local symbols are emitted first, as the ELF
    format requires, and ``sh_info`` is set to the first non-local index.

    `build_elf32be` above cannot do this: every section it writes is
    ``SHT_PROGBITS``, and a symbol table needs its own type, its ``sh_link``
    to a string table, and an entry size. Both builders stay because they
    answer different questions -- that one is "what bytes are in this
    section", this one is "what does this object say about its own symbols".
    """

    ordered = sorted(symbols, key=lambda item: (item[4] != STB_LOCAL,))
    first_global = sum(1 for item in ordered if item[4] == STB_LOCAL) + 1

    strtab = bytearray(b"\x00")
    name_offsets: dict[str, int] = {}
    for name, *_rest in ordered:
        if name not in name_offsets:
            name_offsets[name] = len(strtab)
            strtab.extend(name.encode("ascii") + b"\x00")

    section_names = ["", section, ".symtab", ".strtab", ".shstrtab"]
    shstrtab = b"\x00".join(name.encode("ascii") for name in section_names) + b"\x00"
    shstr_offsets: dict[str, int] = {}
    cursor = 0
    for name in section_names:
        shstr_offsets[name] = cursor
        cursor += len(name.encode("ascii")) + 1

    text_index, strtab_index = 1, 3

    symtab = bytearray(struct.pack(">IIIBBH", 0, 0, 0, 0, 0, 0))
    for name, value, size, kind, binding in ordered:
        symtab.extend(
            struct.pack(
                ">IIIBBH",
                name_offsets[name],
                value,
                size,
                (binding << 4) | kind,
                0,
                text_index,
            )
        )

    offset = ELF_HEADER_SIZE
    text_offset = offset
    offset += len(text)
    symtab_offset = offset
    offset += len(symtab)
    strtab_offset = offset
    offset += len(strtab)
    shstrtab_offset = offset
    offset += len(shstrtab)
    shoff = offset

    elf_header = struct.pack(
        ">16sHHIIIIIHHHHHH",
        b"\x7fELF\x01\x02\x01" + b"\x00" * 9,
        1,
        8,
        1,
        0,
        0,
        shoff,
        0,
        ELF_HEADER_SIZE,
        0,
        0,
        SECTION_HEADER_SIZE,
        5,
        4,
    )

    def header(
        name_off: int,
        sh_type: int,
        sh_flags: int,
        sh_offset: int,
        sh_size: int,
        sh_link: int = 0,
        sh_info: int = 0,
        sh_entsize: int = 0,
    ) -> bytes:
        return struct.pack(
            ">10I",
            name_off,
            sh_type,
            sh_flags,
            0,
            sh_offset,
            sh_size,
            sh_link,
            sh_info,
            4,
            sh_entsize,
        )

    SHT_NULL, SHT_PROGBITS, SHT_SYMTAB, SHT_STRTAB = 0, 1, 2, 3
    headers = [
        struct.pack(">10I", 0, SHT_NULL, 0, 0, 0, 0, 0, 0, 0, 0),
        header(shstr_offsets[section], SHT_PROGBITS, 0x6, text_offset, len(text)),
        header(
            shstr_offsets[".symtab"],
            SHT_SYMTAB,
            0,
            symtab_offset,
            len(symtab),
            sh_link=strtab_index,
            sh_info=first_global,
            sh_entsize=16,
        ),
        header(shstr_offsets[".strtab"], SHT_STRTAB, 0, strtab_offset, len(strtab)),
        header(
            shstr_offsets[".shstrtab"], SHT_STRTAB, 0, shstrtab_offset, len(shstrtab)
        ),
    ]
    return elf_header + text + bytes(symtab) + strtab + shstrtab + b"".join(headers)


SHT_REL = 9
SHN_UNDEF = 0

# Repeated at module scope so `build_relocatable` can name them; the older
# builders above keep their own function-local copies.
SHT_PROGBITS = 1
SHT_SYMTAB = 2
SHT_STRTAB = 3

R_MIPS_32 = 2
R_MIPS_26 = 4
R_MIPS_HI16 = 5
R_MIPS_LO16 = 6


@dataclass(frozen=True)
class SymbolSpec:
    """One `.symtab` entry for `build_relocatable`.

    ``section`` is the section the symbol is defined in, or ``None`` for the
    `SHN_UNDEF` shape a placeholder extern has -- the shape the whole
    relocation-surface synthesis exists to give a value to.
    """

    name: str
    value: int = 0
    size: int = 0
    kind: int = STT_NOTYPE
    binding: int = STB_GLOBAL
    section: str | None = None


@dataclass(frozen=True)
class RelocSpec:
    """One `Elf32_Rel` entry, naming its symbol by name rather than index."""

    section: str
    offset: int
    symbol: str
    type: int


def build_relocatable(
    sections: dict[str, bytes],
    symbols: Sequence[SymbolSpec] = (),
    relocations: Sequence[RelocSpec] = (),
) -> bytes:
    """Return an ELF32 big-endian object with a symtab and `.rel.*` sections.

    `build_object` above writes one code section whose every symbol is
    defined in it; this writes as many sections as the caller names, symbols
    that may be undefined, and real relocation sections linked back to the
    section they apply to. That combination is what a relocation reader has
    to be tested against: an undefined symbol reached from two `.text` sites
    is the exact shape a placeholder extern has in a real object.
    """

    content = list(sections.items())
    section_index = {name: 1 + position for position, name in enumerate(sections)}
    symtab_index = 1 + len(content)
    strtab_index = symtab_index + 1
    rel_sections = [
        name for name in sections if any(item.section == name for item in relocations)
    ]

    ordered = sorted(symbols, key=lambda item: item.binding != STB_LOCAL)
    first_global = sum(1 for item in ordered if item.binding == STB_LOCAL) + 1
    symbol_index = {item.name: 1 + position for position, item in enumerate(ordered)}

    strtab = bytearray(b"\x00")
    name_offsets: dict[str, int] = {}
    for item in ordered:
        if item.name not in name_offsets:
            name_offsets[item.name] = len(strtab)
            strtab.extend(item.name.encode("ascii") + b"\x00")

    symtab = bytearray(struct.pack(">IIIBBH", 0, 0, 0, 0, 0, 0))
    for item in ordered:
        symtab.extend(
            struct.pack(
                ">IIIBBH",
                name_offsets[item.name],
                item.value,
                item.size,
                (item.binding << 4) | item.kind,
                0,
                SHN_UNDEF if item.section is None else section_index[item.section],
            )
        )

    rel_bodies: dict[str, bytearray] = {name: bytearray() for name in rel_sections}
    for entry in relocations:
        rel_bodies[entry.section].extend(
            struct.pack(
                ">II", entry.offset, (symbol_index[entry.symbol] << 8) | entry.type
            )
        )

    names = [
        "",
        *sections,
        ".symtab",
        ".strtab",
        *[f".rel{name}" for name in rel_sections],
        ".shstrtab",
    ]
    shstrtab = bytearray(b"\x00")
    shstr_offsets: dict[str, int] = {"": 0}
    for name in names[1:]:
        if name in shstr_offsets:
            continue
        shstr_offsets[name] = len(shstrtab)
        shstrtab.extend(name.encode("ascii") + b"\x00")

    bodies: list[bytes] = []
    offsets: list[int] = []
    cursor = ELF_HEADER_SIZE
    for _name, blob in content:
        offsets.append(cursor)
        bodies.append(blob)
        cursor += len(blob)
    symtab_offset = cursor
    cursor += len(symtab)
    strtab_offset = cursor
    cursor += len(strtab)
    rel_offsets: dict[str, int] = {}
    for name in rel_sections:
        rel_offsets[name] = cursor
        cursor += len(rel_bodies[name])
    shstrtab_offset = cursor
    cursor += len(shstrtab)
    shoff = cursor

    header_count = len(names)
    elf_header = struct.pack(
        ">16sHHIIIIIHHHHHH",
        b"\x7fELF\x01\x02\x01" + b"\x00" * 9,
        1,
        8,
        1,
        0,
        0,
        shoff,
        0,
        ELF_HEADER_SIZE,
        0,
        0,
        SECTION_HEADER_SIZE,
        header_count,
        header_count - 1,
    )

    def header(
        name_off: int,
        sh_type: int,
        sh_offset: int,
        sh_size: int,
        *,
        flags: int = 0,
        link: int = 0,
        info: int = 0,
        entsize: int = 0,
    ) -> bytes:
        return struct.pack(
            ">10I",
            name_off,
            sh_type,
            flags,
            0,
            sh_offset,
            sh_size,
            link,
            info,
            4,
            entsize,
        )

    headers = [struct.pack(">10I", *([0] * 10))]
    for position, (name, blob) in enumerate(content):
        headers.append(
            header(
                shstr_offsets[name],
                SHT_PROGBITS,
                offsets[position],
                len(blob),
                flags=0x6,
            )
        )
    headers.append(
        header(
            shstr_offsets[".symtab"],
            SHT_SYMTAB,
            symtab_offset,
            len(symtab),
            link=strtab_index,
            info=first_global,
            entsize=16,
        )
    )
    headers.append(
        header(shstr_offsets[".strtab"], SHT_STRTAB, strtab_offset, len(strtab))
    )
    for name in rel_sections:
        headers.append(
            header(
                shstr_offsets[f".rel{name}"],
                SHT_REL,
                rel_offsets[name],
                len(rel_bodies[name]),
                link=symtab_index,
                info=section_index[name],
                entsize=8,
            )
        )
    headers.append(
        header(shstr_offsets[".shstrtab"], SHT_STRTAB, shstrtab_offset, len(shstrtab))
    )

    return (
        elf_header
        + b"".join(bodies)
        + bytes(symtab)
        + bytes(strtab)
        + b"".join(bytes(rel_bodies[name]) for name in rel_sections)
        + bytes(shstrtab)
        + b"".join(headers)
    )
