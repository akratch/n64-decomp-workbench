"""Hand-built ELF32 big-endian objects for `target_audit` tests.

`elf_fixtures.build_elf32be` only emits `SHT_PROGBITS` sections, which is
enough for the padding-safe instruction counter but not for a target audit,
which reads the symbol table and relocation entries directly. This module
is a small superset: a section spec carries its own `sh_type`/`sh_link`/
`sh_info`/`sh_entsize`, and helpers build valid `Elf32_Sym`/`Elf32_Rel`
tables from Python values.

Every fixture here reproduces the *shape* the real cef4c objects measured
against this module were found to have -- a `.rel.rodata` entry per jump
table word pointing at the `.text` section symbol, an FP literal loaded
through `lwc1 %lo(sym)($at)` binding to an `SHN_UNDEF` symbol, a decoy `lw`
through a non-`$at` base register that must *not* be classed as a pool
access -- built from scratch so the test suite carries no game-derived
bytes at all.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass, field

ELF_HEADER_SIZE = 52
SECTION_HEADER_SIZE = 40

SHT_NULL = 0
SHT_PROGBITS = 1
SHT_SYMTAB = 2
SHT_STRTAB = 3
SHT_REL = 9

STB_LOCAL = 0
STB_GLOBAL = 1
STT_NOTYPE = 0
STT_OBJECT = 1
STT_SECTION = 3

SHN_UNDEF = 0

R_MIPS_32 = 2
R_MIPS_HI16 = 5
R_MIPS_LO16 = 6

OP_LUI = 0x0F
OP_LW = 0x23
OP_LWC1 = 0x31
OP_LDC1 = 0x35
REGISTER_AT = 1


def word(opcode: int, rs: int, rt: int, imm: int) -> int:
    """Encode one MIPS I-type word: `opcode rs, rt, imm`."""

    return ((opcode & 0x3F) << 26) | ((rs & 0x1F) << 21) | ((rt & 0x1F) << 16) | (
        imm & 0xFFFF
    )


def words(*values: int) -> bytes:
    return b"".join(struct.pack(">I", value) for value in values)


def sym_info(bind: int, kind: int) -> int:
    return (bind << 4) | kind


def sym_entry(
    *, name_offset: int, value: int = 0, size: int = 0, info: int, shndx: int
) -> bytes:
    return struct.pack(">IIIBBH", name_offset, value, size, info, 0, shndx)


def rel_entry(*, offset: int, sym_index: int, r_type: int) -> bytes:
    return struct.pack(">II", offset, (sym_index << 8) | r_type)


@dataclass
class StringTable:
    """A growable ELF string table: leading NUL, then names, offsets given out."""

    blob: bytearray = field(default_factory=lambda: bytearray(b"\x00"))
    offsets: dict[str, int] = field(default_factory=dict)

    def add(self, name: str) -> int:
        if name == "":
            return 0
        if name in self.offsets:
            return self.offsets[name]
        offset = len(self.blob)
        self.blob += name.encode("ascii") + b"\x00"
        self.offsets[name] = offset
        return offset

    def bytes(self) -> bytes:
        return bytes(self.blob)


@dataclass
class SectionSpec:
    name: str
    content: bytes = b""
    type: int = SHT_PROGBITS
    link: int = 0
    info: int = 0
    entsize: int = 0
    addralign: int = 4


def build_elf32be(sections: list[SectionSpec]) -> bytes:
    """Return a full ELF32 big-endian relocatable object from ``sections``.

    Index 0 is always the mandatory NULL section; ``sections`` follow in
    order (so a spec that names another by index can rely on
    ``1 + position``); `.shstrtab` is generated and appended last.
    """

    names = ["", *[item.name for item in sections], ".shstrtab"]
    shstrtab = bytearray(b"\x00")
    name_offsets: dict[str, int] = {"": 0}
    for name in names[1:]:
        if name in name_offsets:
            continue
        name_offsets[name] = len(shstrtab)
        shstrtab += name.encode("ascii") + b"\x00"

    offset = ELF_HEADER_SIZE
    bodies: list[tuple[SectionSpec, int]] = []
    for item in sections:
        bodies.append((item, offset))
        offset += len(item.content)
    shstrtab_offset = offset
    offset += len(shstrtab)
    shoff = offset

    header_count = 1 + len(sections) + 1
    shstrndx = header_count - 1

    elf_header = struct.pack(
        ">16sHHIIIIIHHHHHH",
        b"\x7fELF\x01\x02\x01" + b"\x00" * 9,
        1,  # ET_REL
        8,  # EM_MIPS
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
        shstrndx,
    )

    def section_header(
        name_off: int,
        sh_type: int,
        sh_offset: int,
        sh_size: int,
        *,
        link: int = 0,
        info: int = 0,
        addralign: int = 0,
        entsize: int = 0,
    ) -> bytes:
        return struct.pack(
            ">10I",
            name_off,
            sh_type,
            0,
            0,
            sh_offset,
            sh_size,
            link,
            info,
            addralign,
            entsize,
        )

    headers = [section_header(0, SHT_NULL, 0, 0)]
    for item, section_offset in bodies:
        headers.append(
            section_header(
                name_offsets[item.name],
                item.type,
                section_offset,
                len(item.content),
                link=item.link,
                info=item.info,
                addralign=item.addralign,
                entsize=item.entsize,
            )
        )
    headers.append(
        section_header(
            name_offsets[".shstrtab"], SHT_STRTAB, shstrtab_offset, len(shstrtab)
        )
    )

    return (
        elf_header
        + b"".join(item.content for item, _offset in bodies)
        + bytes(shstrtab)
        + b"".join(headers)
    )


@dataclass
class PoolSymbol:
    """One FP literal pool site: a name, its `.text` offsets, its opcode."""

    name: str
    hi_offset: int
    lo_offset: int
    opcode: int = OP_LWC1
    base_register: int = REGISTER_AT


def build_target_object(
    *,
    jump_table_words: int,
    rodata_extra_bytes: int,
    pool_symbols: list[PoolSymbol],
    include_decoy: bool = False,
    include_symtab: bool = True,
    rel_text_entsize: int | None = None,
) -> bytes:
    """Build a synthetic `target.o`-shaped object for the truncation heuristic.

    ``jump_table_words`` `.rel.rodata` entries are emitted, each pointing at
    the `.text` section symbol -- the shape `_pool_evidence` reads as a jump
    table. ``rodata_extra_bytes`` bytes follow the table inside `.rodata`:
    zero reproduces the cef4c defect (the section ends exactly at the table
    boundary); nonzero reproduces the fixed object (a literal pool -- or any
    other trailing data -- survives past it). Each ``pool_symbols`` entry
    becomes an `SHN_UNDEF` symbol reached from two `.text` relocations (a
    `%hi` and the `%lo` load through its own base register), the shape the
    literal-pool heuristic looks for when that register is `$at`.
    """

    text_size = max(
        (item.lo_offset + 4 for item in pool_symbols),
        default=0,
    )
    decoy_hi = text_size
    decoy_lo = text_size + 4
    if include_decoy:
        text_size += 8
    text_size = max(text_size, 4)
    # Round up to a 4-byte multiple, which every real MIPS .text already is.
    text_size = (text_size + 3) & ~3

    text = bytearray(text_size)

    def place(offset: int, value: int) -> None:
        struct.pack_into(">I", text, offset, value)

    for item in pool_symbols:
        place(item.hi_offset, word(OP_LUI, 0, item.base_register, 0))
        place(
            item.lo_offset,
            word(item.opcode, item.base_register, 8, 0),
        )
    if include_decoy:
        # A load through $v0 (register 2), not $at: bound to an undefined
        # symbol the same way a real pool site is, and must not be counted
        # as one. Mirrors the real cef4c object's D_ovl0_800D639C site.
        place(decoy_hi, word(OP_LUI, 0, 2, 0))
        place(decoy_lo, word(OP_LW, 2, 3, 0))

    strtab = StringTable()
    # Symbol table index 1: the .text section symbol every jump-table entry's
    # relocation names (index 0 is the mandatory null symbol). The final
    # symbol list built below preserves this order.
    text_symbol_index = 1

    rodata_size = jump_table_words * 4 + rodata_extra_bytes
    rodata = bytes(rodata_size)

    rel_text_entries = bytearray()
    symbol_index_by_name: dict[str, int] = {}
    next_symbol_index = text_symbol_index + 1
    for item in pool_symbols:
        if item.name not in symbol_index_by_name:
            symbol_index_by_name[item.name] = next_symbol_index
            next_symbol_index += 1
    if include_decoy:
        symbol_index_by_name["D_decoy"] = next_symbol_index
        next_symbol_index += 1

    for item in pool_symbols:
        index = symbol_index_by_name[item.name]
        rel_text_entries += rel_entry(
            offset=item.hi_offset, sym_index=index, r_type=R_MIPS_HI16
        )
        rel_text_entries += rel_entry(
            offset=item.lo_offset, sym_index=index, r_type=R_MIPS_LO16
        )
    if include_decoy:
        index = symbol_index_by_name["D_decoy"]
        rel_text_entries += rel_entry(
            offset=decoy_hi, sym_index=index, r_type=R_MIPS_HI16
        )
        rel_text_entries += rel_entry(
            offset=decoy_lo, sym_index=index, r_type=R_MIPS_LO16
        )

    # Section order: .text, .rel.text, .rodata, .rel.rodata, .symtab, .strtab
    # -- indices 1..6 (0 is the mandatory NULL section).
    TEXT_INDEX = 1
    RODATA_INDEX = 3
    SYMTAB_INDEX = 5
    STRTAB_INDEX = 6

    rel_rodata_entries = bytearray()
    for slot in range(jump_table_words):
        rel_rodata_entries += rel_entry(
            offset=slot * 4, sym_index=text_symbol_index, r_type=R_MIPS_32
        )

    symbols = [sym_entry(name_offset=0, info=0, shndx=0)]
    symbols.append(
        sym_entry(
            name_offset=0,
            info=sym_info(STB_LOCAL, STT_SECTION),
            shndx=TEXT_INDEX,
        )
    )
    for item in pool_symbols:
        if symbol_index_by_name[item.name] != len(symbols):
            continue  # already emitted (a name reused across sites)
        symbols.append(
            sym_entry(
                name_offset=strtab.add(item.name),
                info=sym_info(STB_GLOBAL, STT_OBJECT),
                shndx=SHN_UNDEF,
            )
        )
    if include_decoy and symbol_index_by_name["D_decoy"] == len(symbols):
        symbols.append(
            sym_entry(
                name_offset=strtab.add("D_decoy"),
                info=sym_info(STB_GLOBAL, STT_OBJECT),
                shndx=SHN_UNDEF,
            )
        )

    specs = [
        SectionSpec(".text", bytes(text), type=SHT_PROGBITS),
        SectionSpec(
            ".rel.text",
            bytes(rel_text_entries),
            type=SHT_REL,
            link=SYMTAB_INDEX,
            info=TEXT_INDEX,
            entsize=rel_text_entsize if rel_text_entsize is not None else 8,
        ),
        SectionSpec(".rodata", rodata, type=SHT_PROGBITS),
        SectionSpec(
            ".rel.rodata",
            bytes(rel_rodata_entries),
            type=SHT_REL,
            link=SYMTAB_INDEX,
            info=RODATA_INDEX,
            entsize=8,
        ),
    ]
    if include_symtab:
        specs.append(
            SectionSpec(
                ".symtab",
                b"".join(symbols),
                type=SHT_SYMTAB,
                link=STRTAB_INDEX,
                info=len(symbols),
                entsize=16,
            )
        )
        specs.append(SectionSpec(".strtab", strtab.bytes(), type=SHT_STRTAB))

    return build_elf32be(specs)
