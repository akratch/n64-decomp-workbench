"""A minimal ELF32 big-endian object builder for ELF-reading test fixtures.

Deliberately hand-rolled rather than shelling out to a real assembler: the
workbench's own test suite must not depend on a MIPS toolchain being
installed, and the byte layout this module writes is simple enough (one
NULL section, the caller's sections, one `.shstrtab`) to encode directly and
keep honest.
"""

from __future__ import annotations

import struct

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
