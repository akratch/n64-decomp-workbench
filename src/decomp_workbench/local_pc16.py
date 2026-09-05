"""Authenticate local REL PC16 destinations without changing comparison bytes."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from .elf import ElfFormatError, Reloc, read_elf
from .elf_symbols import SymbolExtent
from .model import Instruction


def _nonlinking_branch(word: int) -> bool:
    opcode = word >> 26
    rt = (word >> 16) & 31
    if opcode in {4, 5, 20, 21}:  # beq/bne and likely forms
        return True
    if opcode in {6, 7, 22, 23}:  # blez/bgtz and likely forms
        return rt == 0
    if opcode == 1:  # regimm, but not branch-and-link calls
        return rt in {0, 1, 2, 3}
    return opcode == 17 and ((word >> 21) & 31) == 8 and rt in {0, 1, 2, 3}


def annotate_local_pc16(
    path: str | Path,
    instructions: list[Instruction],
    extent: SymbolExtent | None,
) -> list[Instruction]:
    """Add alignment hints only for ELF-proved branches inside the owned function.

    MIPS REL stores a signed, scaled addend in the instruction. Applying the
    relocation yields a runtime destination of ``S + signext(imm16)*4 + 4``;
    the usual encoded addend is -1, not zero. Objdump's printed destination
    is therefore not authoritative. Unknown, external, linking, malformed,
    out-of-range, or text/ELF-inconsistent cases retain their original view.
    """
    if extent is None or extent.stop is None:
        return instructions
    if not any(r.kind == "R_MIPS_PC16" for i in instructions for r in i.relocations):
        return instructions
    try:
        elf = read_elf(path)
    except (OSError, ElfFormatError):
        return instructions
    # ET_REL, EM_MIPS: no executable VMA or alternative relocation ABI guesses.
    if elf.data[16:20] != b"\x00\x01\x00\x08" or elf.malformed_reloc_sections:
        return instructions
    section = elf.section(extent.section)
    body = elf.section_bytes(extent.section)
    if (
        section is None
        or body is None
        or not section.flags & 4  # SHF_EXECINSTR
        or section.addr != 0
        or not 0 <= extent.start < extent.stop <= len(body)
        or extent.start % 4
        or extent.stop % 4
    ):
        return instructions
    owners = [s for s in elf.symbols if s.name == extent.name]
    if len(owners) != 1 or owners[0].shndx != section.index:
        return instructions
    if owners[0].value != extent.start:
        return instructions
    if owners[0].size and owners[0].value + owners[0].size != extent.stop:
        return instructions
    by_offset: dict[int, list[Reloc]] = {}
    for relocation in elf.relocations_for(extent.section):
        by_offset.setdefault(relocation.offset, []).append(relocation)
    addresses = {instruction.address for instruction in instructions}
    annotated = []
    for instruction in instructions:
        offset = instruction.address
        raw = by_offset.get(offset, [])
        destination = None
        if (
            extent.contains(offset)
            and offset % 4 == 0
            and len(raw) == 1
            and raw[0].type == 10
            and len(instruction.relocations) == 1
            and instruction.relocations[0].kind == "R_MIPS_PC16"
            and instruction.relocations[0].offset == offset
            and instruction.word_value
            == int.from_bytes(body[offset : offset + 4], "big")
            and _nonlinking_branch(instruction.word_value)
        ):
            symbol = elf.symbol(raw[0].sym_index)
            if (
                symbol is not None
                and symbol.shndx == section.index
                and symbol.name == instruction.relocations[0].symbol
                and extent.contains(symbol.value)
                and symbol.value % 4 == 0
            ):
                addend = instruction.word_value & 0xFFFF
                if addend & 0x8000:
                    addend -= 0x10000
                resolved = symbol.value + addend * 4 + 4
                displacement = resolved - offset - 4
                if (
                    extent.contains(resolved)
                    and resolved in addresses
                    and displacement % 4 == 0
                    and -0x8000 <= displacement // 4 <= 0x7FFF
                ):
                    destination = resolved
        annotated.append(replace(instruction, local_branch_destination=destination))
    return annotated
