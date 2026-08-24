"""Where one function starts and stops, read from the object's own symbol table.

``--disassemble=NAME`` narrows GNU objdump to one function, and the workbench
then re-selects that function out of the printed text by watching for
``<name>:`` labels. That second step is where a whole campaign's ``--symbol``
evidence went wrong: **a label is not a function boundary.**

A target object extracted from a ROM by splat carries a symbol for every
jump-table destination inside the body it belongs to -- ``jtgt_ovl0_800CF05C``
and forty-four siblings, all ``STT_NOTYPE``, all local, all *inside*
``func_ovl0_800CEF4C``. objdump prints every one of them as a ``<label>:``
header, so a parser that ends the selection at the first label carved 68
instructions out of an 1,868-instruction function and compared them against a
candidate's whole 1,866. The reported ``words=1799 opcodes=1798 gaps=1798``
was not a comparison of two functions at all; it was a comparison of a
function's prologue against a whole function, and it read as a broken
candidate rather than a broken selector.

The fix is to stop inferring the boundary from printed text when the object
itself knows it. This module reads the ELF32 big-endian symbol table and
answers the only question that matters:

    where, in section-relative bytes, does this symbol's code begin and end?

Two rules, in order:

* ``st_size`` when the producer set it. IDO sets it for every function it
  compiles, so a candidate object built from C is exact on the first rule.
* Otherwise the next ``STT_FUNC`` symbol in the same section. Assembly-defined
  and splat-extracted symbols routinely carry ``st_size == 0``; the *type* is
  still the honest signal, and it is exactly the one the interior labels do
  not have. A jump-table destination is ``STT_NOTYPE`` and therefore never
  ends a function here.
* Otherwise the next *externally visible* symbol -- global or weak binding --
  in the same section. A handwritten-``.s`` object has no ``STT_FUNC`` at all:
  every one of its functions is a bare ``.globl`` label, ``STT_NOTYPE`` and
  size 0, so the ``STT_FUNC`` rule alone ran the first function's extent to
  the end of the section and swallowed every sibling after it. The *binding*
  is what separates the two ``STT_NOTYPE`` populations: a function another
  translation unit can call is global or weak, and a jump-table destination
  or local branch target is ``STB_LOCAL``. Local symbols therefore still
  never end a function, which is the rule this module exists to keep.

Everything else -- a stripped object, a symbol that is not in the table, a file
that is not an ELF this reader understands -- returns ``None`` so the caller
falls back to the printed-text rule rather than turning a coarse answer into a
hard failure.

This module reads ELF32 big-endian bytes with its own minimal struct code, and
so do :mod:`decomp_workbench.elf_instructions`, :mod:`decomp_workbench.ldmap`,
:mod:`decomp_workbench.line_probe`, :mod:`decomp_workbench.objdump`. Each
answers one narrow question and each declines rather than raising where a
general reader would refuse the file. :mod:`decomp_workbench.elf` is the
intended future home for all of them; folding them in changes five distinct
failure behaviours, so it is deliberate work rather than a refactor to do in
passing.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass
from pathlib import Path

__all__ = [
    "STT_FUNC",
    "SymbolExtent",
    "read_symbols",
    "symbol_extent",
]

_ELF_MAGIC = b"\x7fELF"
_ELFCLASS32 = 1
_ELFDATA2MSB = 2

_SHT_SYMTAB = 2
_SHT_NOBITS = 8

#: ``STT_FUNC``: the low nibble of ``st_info``. The symbol type that ends
#: another function's body outright -- see this module's docstring for why the
#: type, and not the mere presence of a label, is the boundary.
STT_FUNC = 2

#: ``STT_SECTION`` and ``STT_FILE``: the two types that name something other
#: than a datum in the section, and so never bound a function even when they
#: are globally bound.
STT_SECTION = 3
STT_FILE = 4

#: The bindings of a symbol another translation unit can reach. A sizeless,
#: typeless symbol with one of these is a handwritten-assembly function entry;
#: the same symbol with ``STB_LOCAL`` is an interior label.
STB_GLOBAL = 1
STB_WEAK = 2
EXTERNAL_BINDINGS = frozenset({STB_GLOBAL, STB_WEAK})


@dataclass(frozen=True)
class SymbolExtent:
    """One symbol's section-relative byte range, and how it was decided.

    ``stop is None`` means "to the end of the section": the symbol is the last
    function entry in it and declared no size. That is still a usable extent --
    it excludes everything *before* the symbol, which is the half that carved
    a prologue out of a target object -- and it is honest about the half it
    cannot bound.
    """

    name: str
    section: str
    start: int
    stop: int | None
    #: ``size`` when ``st_size`` bounded it, ``next-function`` when the next
    #: ``STT_FUNC`` did, ``next-global`` when an untyped but externally bound
    #: sibling did (the handwritten-assembly shape), ``section-end`` when
    #: nothing did.
    basis: str

    def contains(self, offset: int) -> bool:
        if offset < self.start:
            return False
        return self.stop is None or offset < self.stop


@dataclass(frozen=True)
class ElfSymbol:
    """One symbol table entry, reduced to what a boundary question needs."""

    name: str
    value: int
    size: int
    info: int
    section_index: int

    @property
    def kind(self) -> int:
        return self.info & 0xF

    @property
    def binding(self) -> int:
        return self.info >> 4

    @property
    def is_function(self) -> bool:
        return self.kind == STT_FUNC

    @property
    def starts_a_function(self) -> bool:
        """True when this symbol can only be another function's entry point.

        Either it says so (``STT_FUNC``), or it is a named, externally bound
        symbol of no particular type -- which is all a handwritten-assembly
        function ever is. Section and file symbols are excluded because they
        name the container, not anything inside it.
        """

        if self.is_function:
            return True
        return bool(
            self.name
            and self.binding in EXTERNAL_BINDINGS
            and self.kind not in (STT_SECTION, STT_FILE)
        )


def _sections(data: bytes) -> list[tuple[str, int, int, int, int, int]] | None:
    """Return ``(name, type, offset, size, link, entsize)`` per section header.

    ``None`` for anything that is not the ELF32 big-endian relocatable shape
    this reader was written against. A caller that gets ``None`` must fall
    back, never fail: reading a symbol table is a refinement of the printed
    disassembly, not a precondition for it.
    """

    if len(data) < 52 or data[:4] != _ELF_MAGIC:
        return None
    if data[4] != _ELFCLASS32 or data[5] != _ELFDATA2MSB:
        return None
    try:
        (e_shoff,) = struct.unpack_from(">I", data, 0x20)
        (e_shentsize,) = struct.unpack_from(">H", data, 0x2E)
        (e_shnum,) = struct.unpack_from(">H", data, 0x30)
        (e_shstrndx,) = struct.unpack_from(">H", data, 0x32)
    except struct.error:
        return None
    if e_shoff == 0 or e_shnum == 0 or e_shstrndx >= e_shnum:
        return None

    raw: list[tuple[int, int, int, int, int, int]] = []
    for index in range(e_shnum):
        offset = e_shoff + index * e_shentsize
        if offset + 40 > len(data):
            return None
        (
            name_off,
            sh_type,
            _flags,
            _addr,
            sh_offset,
            sh_size,
            sh_link,
            _info,
            _align,
            sh_entsize,
        ) = struct.unpack_from(">10I", data, offset)
        raw.append((name_off, sh_type, sh_offset, sh_size, sh_link, sh_entsize))

    _name_off, _type, str_offset, str_size, _link, _entsize = raw[e_shstrndx]
    shstrtab = data[str_offset : str_offset + str_size]

    def name_at(offset: int) -> str:
        end = shstrtab.find(b"\x00", offset)
        if end < 0:
            end = len(shstrtab)
        return shstrtab[offset:end].decode("ascii", errors="replace")

    return [
        (name_at(entry[0]), entry[1], entry[2], entry[3], entry[4], entry[5])
        for entry in raw
    ]


def read_symbols(path: str | Path) -> tuple[list[ElfSymbol], dict[str, int]] | None:
    """Return every symtab entry plus a ``section name -> index`` map.

    ``None`` when the file is not a readable ELF32 big-endian object or has no
    symbol table at all (a fully stripped object). Both are ordinary states
    for an input this workbench accepts, so neither raises.
    """

    try:
        data = Path(path).read_bytes()
    except OSError:
        return None
    sections = _sections(data)
    if sections is None:
        return None
    indices = {name: index for index, (name, *_rest) in enumerate(sections)}
    symtab = next(
        (entry for entry in sections if entry[1] == _SHT_SYMTAB),
        None,
    )
    if symtab is None:
        return None
    _name, _type, sym_offset, sym_size, sym_link, sym_entsize = symtab
    if sym_entsize < 16 or sym_link >= len(sections):
        return None
    _sname, stype, str_offset, str_size, _slink, _sentsize = sections[sym_link]
    if stype == _SHT_NOBITS:
        return None
    strtab = data[str_offset : str_offset + str_size]

    def name_at(offset: int) -> str:
        if offset >= len(strtab):
            return ""
        end = strtab.find(b"\x00", offset)
        if end < 0:
            end = len(strtab)
        return strtab[offset:end].decode("ascii", errors="replace")

    symbols: list[ElfSymbol] = []
    for cursor in range(sym_offset, sym_offset + sym_size, sym_entsize):
        if cursor + 16 > len(data):
            break
        st_name, st_value, st_size, st_info, _other, st_shndx = struct.unpack_from(
            ">IIIBBH", data, cursor
        )
        symbols.append(
            ElfSymbol(
                name=name_at(st_name),
                value=st_value,
                size=st_size,
                info=st_info,
                section_index=st_shndx,
            )
        )
    return symbols, indices


def symbol_extent(
    path: str | Path, symbol: str, *, section: str = ".text"
) -> SymbolExtent | None:
    """Return where ``symbol``'s code lives in ``section``, or ``None``.

    ``None`` means "this object cannot answer", and the caller must fall back
    to the printed-text rule: no symbol table, no such symbol, the symbol lives
    in a different section, or the file is not the ELF shape read here.

    The case-insensitive fallback mirrors `parse_disassembly`'s: a Pascal-era
    frontend folds identifiers to lower case, so a function authored as ``Foo``
    is ``foo`` in the object. It fires only on a *unique* fold, because a
    non-unique one is a guess and this function's whole value is that it does
    not guess.
    """

    read = read_symbols(path)
    if read is None:
        return None
    symbols, indices = read
    section_index = indices.get(section)
    if section_index is None:
        return None
    in_section = [item for item in symbols if item.section_index == section_index]
    match = next((item for item in in_section if item.name == symbol), None)
    if match is None:
        folded = [
            item for item in in_section if item.name.casefold() == symbol.casefold()
        ]
        if len(folded) != 1:
            return None
        match = folded[0]
    if match.size:
        return SymbolExtent(
            name=match.name,
            section=section,
            start=match.value,
            stop=match.value + match.size,
            basis="size",
        )
    # No declared size: the next symbol that can only be another function's
    # entry bounds it. Interior labels -- jump-table destinations, local
    # branch targets -- are local and deliberately do not, which is the entire
    # defect this module fixes.
    successors = [
        item
        for item in in_section
        if item.starts_a_function and item.value > match.value
    ]
    if successors:
        nearest = min(successors, key=lambda item: (item.value, not item.is_function))
        return SymbolExtent(
            name=match.name,
            section=section,
            start=match.value,
            stop=nearest.value,
            basis="next-function" if nearest.is_function else "next-global",
        )
    return SymbolExtent(
        name=match.name,
        section=section,
        start=match.value,
        stop=None,
        basis="section-end",
    )
