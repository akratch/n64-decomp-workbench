"""A minimal, honest ELF32 object writer for line-probe test fixtures.

`decomp_workbench.line_probe` reads `.text` and `.symtab` directly with
`struct`, without objdump. These fixtures build just enough of a real ELF32
object - one NULL section, one PROGBITS `.text`, one SYMTAB `.symtab`, and the
two string tables it needs - to exercise that reader honestly, the same way
`tests/mips_asm.py` renders real objdump text for the object-comparison
tests. The bytes are synthetic and redistributable.
"""

from __future__ import annotations

import struct


def _cstr_table(names: list[str]) -> tuple[bytes, dict[str, int]]:
    blob = b"\x00"
    offsets: dict[str, int] = {}
    for name in names:
        offsets[name] = len(blob)
        blob += name.encode("utf-8") + b"\x00"
    return blob, offsets


def build_elf32(
    text_bytes: bytes,
    symbols: list[tuple[str, int, int]] = (),  # type: ignore[assignment]
    *,
    big_endian: bool = True,
) -> bytes:
    """Return a relocatable ELF32 object with one `.text` and `symbols`.

    `symbols` is `(name, value, size)`; every symbol is `STT_FUNC` defined in
    `.text`. Passing no symbols still produces a valid `.symtab` holding only
    the mandatory null entry, so whole-`.text` extraction is always exercised
    the same way a `--function` lookup would be.
    """

    endian = ">" if big_endian else "<"
    shstrtab_blob, shstr_off = _cstr_table([".text", ".symtab", ".strtab", ".shstrtab"])
    symbol_names = [name for name, _value, _size in symbols]
    strtab_blob, str_off = _cstr_table(symbol_names)

    header_size = 52
    text_off = header_size
    text_size = len(text_bytes)

    sym_entries = [(0, 0, 0, 0, 0)] + [
        (str_off[name], value, size, (1 << 4) | 2, 1) for name, value, size in symbols
    ]
    symtab_blob = b"".join(
        struct.pack(endian + "IIIBBH", name, value, size, info, 0, shndx)
        for name, value, size, info, shndx in sym_entries
    )

    symtab_off = text_off + text_size
    strtab_off = symtab_off + len(symtab_blob)
    shstrtab_off = strtab_off + len(strtab_blob)
    shoff = shstrtab_off + len(shstrtab_blob)

    section_headers = [
        (0, 0, 0, 0, 0, 0, 0, 0, 0, 0),  # SHT_NULL
        (shstr_off[".text"], 1, 0x6, 0, text_off, text_size, 0, 0, 4, 0),
        (
            shstr_off[".symtab"],
            2,
            0,
            0,
            symtab_off,
            len(symtab_blob),
            3,  # sh_link -> .strtab
            1,
            4,
            16,
        ),
        (shstr_off[".strtab"], 3, 0, 0, strtab_off, len(strtab_blob), 0, 0, 1, 0),
        (shstr_off[".shstrtab"], 3, 0, 0, shstrtab_off, len(shstrtab_blob), 0, 0, 1, 0),
    ]
    section_blob = b"".join(
        struct.pack(endian + "IIIIIIIIII", *entry) for entry in section_headers
    )

    ei_data = 2 if big_endian else 1
    e_ident = b"\x7fELF" + bytes([1, ei_data, 1]) + b"\x00" * 9
    header = e_ident + struct.pack(
        endian + "HHIIIIIHHHHHH",
        1,  # e_type: ET_REL
        8,  # e_machine: EM_MIPS
        1,  # e_version
        0,  # e_entry
        0,  # e_phoff
        shoff,  # e_shoff
        0,  # e_flags
        header_size,  # e_ehsize
        0,  # e_phentsize
        0,  # e_phnum
        40,  # e_shentsize
        len(section_headers),  # e_shnum
        4,  # e_shstrndx
    )
    return (
        header + text_bytes + symtab_blob + strtab_blob + shstrtab_blob + section_blob
    )
