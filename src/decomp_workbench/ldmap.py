"""Read a linked project's symbols: from its ``ld -Map``, and from its ELF.

S0's hand rehearsal (``shift-instrumentation/s0``, DKR ``us.v77``) proved the
whole shiftability-audit concept by hand before any of this existed: shift a
cascade linker script, relink, and diff the two images with a linker map open
in the other window. Every step of that hand process read the map text with a
throwaway regex -- once to find where ``.text`` of ``entrypoint.s.o`` ended
(the insertion point), once to resolve ``gRaceCheckFinishChecksum`` to a ROM
offset (a checksum-patched word's location), once to build the
address-to-symbol table the residue dump attributed unexplained words
against. This module is that regex, done once and tested, so the commands
that follow (``shift audit``, ``shift rehearse``) start from one parsed map
instead of each growing its own.

Four things this module has to get right that a naive "extract addr + name"
scan does not:

* **The VRAM<->ROM mapping is derived, not hardcoded.** DKR's cascade linker
  script (``mods/dkr.custom.ld``) places every segment but ``.main`` by
  chaining ``__romPos``; the only sections whose ROM position differs from
  their runtime address print ``load address 0x...`` in the map, because
  that is exactly when the section's script used ``AT()`` (``.main``,
  ``.main_bss``, ``.assets_lut``, ``.assets`` in DKR -- the two asset
  segments are DMA'd from ROM on demand and are never VRAM-resident at link
  time, which is also why ``.assets`` and ``.assets_lut`` share a VMA start
  with each other: neither one is really "at" that VRAM address
  simultaneously). A section that prints no load address is *not* assumed to
  have LMA == VMA here: GNU ld's real default LMA for such a section is
  "contiguous after the previous section's LMA in the same region", which
  can differ from VMA in a script this module has not seen. So
  :meth:`LdMap.rom_for_vram` / :meth:`LdMap.vram_for_rom` only resolve
  addresses inside a section that declared ``AT()`` explicitly, and return
  ``None`` rather than guess elsewhere.
* **A shared VMA start is not always the same shape.** DKR's
  ``.assets_lut``/``.assets`` pair (above) is one section genuinely nested
  inside another. An N64 overlay group -- several output sections a cascade
  script places at *one* shared VMA as mutually exclusive runtime
  alternatives, never resident together (Banjo-Kazooie's
  ``.CC``/``.GV``/``.MMM`` and eleven more all start at ``0x803863f0``, each
  with its own distinct ``AT()`` load address) -- looks identical from
  extents alone. :meth:`LdMap.section_containing` / :meth:`LdMap.rom_for_vram`
  / :meth:`LdMap.vram_for_rom` cannot tell the two apart and always resolve
  through the smallest candidate, correct for nesting and arbitrary for an
  overlay group; :meth:`LdMap.sections_containing` /
  :meth:`LdMap.sections_loaded_at` hand back every candidate instead of
  picking one, for a caller that needs the honest answer.
* **A symbol name is not unique across a map.** The cascade script
  reassigns ``__romPos`` once per segment as it walks the image, so the raw
  symbol stream holds it dozens of times at different addresses. A caller
  that asks for a symbol *by name* (the movement audit, a ``--census``-style
  lookup) wants the placement the map ended with, not an arbitrary one --
  the same last-write-wins rule the S0 spike's own ``census.py`` used (a
  plain ``dict`` built by iterating the symbol lines in order), which is
  what let its movement audit report "``main_BSS_END`` moved by 0x10"
  without qualifying which of the map's many ``main_BSS_END``-shaped lines
  it meant.
* **The linker's own location-counter updates are not symbols.** A line like
  ``. = ALIGN (., 0x10)`` shares a symbol line's exact shape -- an address
  followed by ``NAME = expression`` -- but ``.`` is not a name a caller can
  look up, and keeping it would collide every alignment padding in the map
  under one key and break every name-keyed lookup this module offers.
* **Tiling gaps are reported, not raised.** A gap between two input-section
  extents is sometimes real (an unaccounted hole) and sometimes ``. =
  ALIGN`` filler that the map prints as a separate ``*fill*`` pseudo-record
  this parser does not carry as an input section. Deciding which is a job
  for the caller, with the symbols around the gap in evidence --
  :func:`audit_tiling` hands back the coordinates and nothing more.

**The ELF half (WB-143).** A linker map answers "what name is at what
address" and nothing else. S6's pilotwings64 experiment
(``s6/PW64-SHIFT-CONFIG.md`` §4.4) needed three more facts per symbol, and
none of them is printable in a map: whether a name is *object-backed* (owned
by a real output section) or *absolute* (``SHN_ABS`` -- a linker-script
assignment, which by construction cannot follow a layout), what the symbol's
**size** is, and what its **type** is. `parse_elf_symbols` reads exactly
those out of the linked ELF's ``.symtab``.

The size field is the one that turned a hand experiment into a rule. When a
linker-script assignment overrides an object's definition of the same name --
splat's ``undefined_syms_auto.txt`` writing ``D_803571F0 = 0x803571F0;`` over
the ``.bss`` object that already defines it -- GNU ld emits **one** symbol,
typed ``SHN_ABS``, and *keeps the overridden definition's ``st_size`` and
``st_type``*. So an absolute symbol carrying a non-zero size is an absolute
symbol that shadowed a real definition, and that is visible in the shipped
link with no ablation, no rebuild and no second ELF. Measured on pw64's
37-pin ``undefined_syms_auto.txt``: exactly the ten pins S6 proved redundant
by ablation carry a size (4 to 5,168 bytes), and the other twenty-seven carry
zero. See `ElfSymbol.shadows_definition`.

Parsing rather than shelling out to ``nm`` is a deliberate choice with one
decisive reason: ``nm``'s default output does not carry ``st_size`` at all,
which is the discriminator above. The flags that would print it
(``--print-size``/``-S``) differ between GNU binutils and the llvm ``nm`` that
ships on macOS, and either way a subprocess makes the answer depend on which
cross-toolchain happens to be on ``PATH`` at audit time -- for a command whose
whole point is reading a build somebody else produced. The parse is
~60 lines of `struct`, has no dependency beyond the standard library, and is
tested against a handcrafted ELF built byte by byte in the test module.
"""

from __future__ import annotations

import re
import struct
from bisect import bisect_right
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from itertools import pairwise
from pathlib import Path
from typing import Any

__all__ = [
    "ELF_SYMBOL_BINDINGS",
    "ELF_SYMBOL_KINDS",
    "SHN_ABS",
    "SHN_COMMON",
    "SHN_LORESERVE",
    "SHN_UNDEF",
    "ElfFormatError",
    "ElfSection",
    "ElfSymbol",
    "ElfSymbols",
    "InputSection",
    "LdMap",
    "LinkerSymbol",
    "MovementAudit",
    "OutputSection",
    "SymbolMovement",
    "TilingGap",
    "audit_symbol_movement",
    "audit_tiling",
    "parse_elf_symbols",
    "parse_ld_map",
    "read_elf_symbols",
    "read_ld_map",
]

#: The heading GNU ld prints ahead of the section-by-section body. Real map
#: files always have one; a handcrafted excerpt in a test usually will not,
#: and is read from its first line instead. See `parse_ld_map`.
_MAP_HEADER = "Linker script and memory map"

#: An output-section header: ``NAME  VMA  SIZE`` with an optional trailing
#: ``load address LMA`` when the section's script used ``AT()``. No leading
#: whitespace on a real map line, but the caller checks that before matching
#: (see `parse_ld_map`) so this pattern stays permissive.
_OUTPUT_SECTION_RE = re.compile(
    r"^\s*(?P<name>\.\S+)\s+0x(?P<vma>[0-9a-fA-F]+)\s+0x(?P<size>[0-9a-fA-F]+)"
    r"(?:\s+load address\s+0x(?P<load>[0-9a-fA-F]+))?\s*$"
)

#: One object's contribution to an output section: ``NAME  VMA  SIZE  PATH``,
#: indented one level under its output section's header.
_INPUT_SECTION_RE = re.compile(
    r"^\s*(?P<name>\.\S+)\s+0x(?P<vma>[0-9a-fA-F]+)\s+0x(?P<size>[0-9a-fA-F]+)"
    r"\s+(?P<path>\S+)\s*$"
)

#: A symbol-table row: an address, then either a bare name (a plain symbol)
#: or ``NAME = expression`` (a linker assignment). Which one `rest` is gets
#: sorted out after the match; the two share this one shape.
_SYMBOL_RE = re.compile(r"^\s*0x(?P<address>[0-9a-fA-F]+)\s+(?P<rest>\S.*?)\s*$")

#: The data half of a wrapped section-name line: two ``0x...`` tokens, with
#: no leading section name because that already went out on the line above.
#: Matches both the output-section shape (``VMA SIZE [load address LMA]``)
#: and the input-section shape (``VMA SIZE PATH``) -- both start this way.
_CONTINUATION_RE = re.compile(r"^\s+0x[0-9a-fA-F]+\s+0x[0-9a-fA-F]+")


@dataclass(frozen=True)
class OutputSection:
    """One output section's placement: ``NAME  VMA  SIZE``, plus its LMA if AT()'d."""

    name: str
    vma: int
    size: int
    #: The ROM (or other load-time) address, when the section's script used
    #: ``AT()``. ``None`` means the map printed no ``load address`` line for
    #: this section -- not "load address equals VMA"; see the module
    #: docstring for why that default is not assumed here.
    load_address: int | None

    @property
    def end(self) -> int:
        return self.vma + self.size

    def contains(self, address: int) -> bool:
        """Whether `address` falls inside this section's VMA extent.

        A zero-size section (an output section every input contribution to
        which was itself zero-size) contains only its own start address,
        rather than nothing: that is what lets `LdMap.section_containing`
        still resolve the boundary address of an empty section.
        """

        if self.size == 0:
            return address == self.vma
        return self.vma <= address < self.end

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "vma": self.vma,
            "size": self.size,
            "load_address": self.load_address,
        }


@dataclass(frozen=True)
class InputSection:
    """One object's contribution to an output section.

    ``name`` and ``output_section`` are different things whenever the
    project's script concatenates unlike input sections into one output
    section -- which a shift-hardened cascade script does on purpose. DKR's
    ``.main`` output section is built from ``.text``, ``.rodata``, ``.data``
    and more, one after another, so ``entrypoint.s.o`` contributes *two*
    records with ``output_section == ".main"`` (a ``.text`` one and a
    zero-size ``.data`` one): only ``name`` tells them apart.
    """

    name: str
    output_section: str
    vma: int
    size: int
    object_path: str

    @property
    def end(self) -> int:
        return self.vma + self.size

    def contains(self, address: int) -> bool:
        if self.size == 0:
            return address == self.vma
        return self.vma <= address < self.end

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "output_section": self.output_section,
            "vma": self.vma,
            "size": self.size,
            "object_path": self.object_path,
        }


@dataclass(frozen=True)
class LinkerSymbol:
    """One symbol-table row: a name placed at an address.

    ``is_assignment`` tells a plain symbol (emitted by the assembler, one
    per label) from a linker-script assignment (``NAME = expression``, one
    per ``undefined_syms``-style derivation or segment boundary). Both place
    a name at an address and both answer a name-keyed lookup the same way;
    the flag is for a caller that cares *how* the name got there -- DKR's
    ``gMainMemoryPool = main_BSS_END`` is a derived pin and ``D_B0000574 =
    0xb0000574`` is a hardcoded one, and only the assignment shape can be
    either.
    """

    name: str
    address: int
    is_assignment: bool
    #: The right-hand side text for an assignment (``"main_BSS_END"``,
    #: ``"ABSOLUTE ((main_BSS_END - main_BSS_START))"``, ...). ``None`` for
    #: a plain symbol, which has no expression to carry.
    expression: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "address": self.address,
            "is_assignment": self.is_assignment,
            "expression": self.expression,
        }


@dataclass
class LdMap:
    """One parsed linker map: its sections, input records, and symbols.

    Not frozen -- but the three parsed fields below stay tuples, so nothing
    downstream can mutate a record in place. What mutability buys here is
    `__post_init__` building two small lookup indices once, at parse time,
    rather than re-sorting on every call: a rehearsal walks a whole ROM
    image word by word (S0's spike did ~2.8M of them), and
    `symbol_containing` needs to answer each one in ``O(log n)``, not with a
    fresh ``O(n log n)`` sort per word.
    """

    path: str | None
    sections: tuple[OutputSection, ...]
    input_sections: tuple[InputSection, ...]
    symbols: tuple[LinkerSymbol, ...]

    def __post_init__(self) -> None:
        by_name: dict[str, LinkerSymbol] = {}
        for symbol in self.symbols:
            # Last write wins -- see the module docstring's second point.
            by_name[symbol.name] = symbol
        by_address = tuple(sorted(self.symbols, key=lambda item: item.address))
        self._by_name: dict[str, LinkerSymbol] = by_name
        self._by_address: tuple[LinkerSymbol, ...] = by_address
        self._addresses: tuple[int, ...] = tuple(item.address for item in by_address)

    def symbol(self, name: str) -> LinkerSymbol | None:
        """Return one symbol's last-written placement, or ``None``."""

        return self._by_name.get(name)

    def symbol_names(self) -> frozenset[str]:
        """The distinct names this map defines (each keyed to its last address)."""

        return frozenset(self._by_name)

    def symbols_sorted(self) -> tuple[LinkerSymbol, ...]:
        """Every symbol row, in ascending address order (duplicates included).

        Unlike `symbol`, this is not deduplicated by name: it is the raw
        placement stream, in the order a whole-image walk wants it.
        """

        return self._by_address

    def symbol_containing(self, address: int) -> tuple[LinkerSymbol, int] | None:
        """Return the nearest symbol at or below ``address``, with its offset.

        A linker map carries no symbol *size*, unlike an ELF symbol table,
        so "containing" is the same approximation the S0 spike's
        ``census.py`` used: the nearest symbol at or below the address,
        unconditionally, whether or not it actually extends that far.
        ``None`` only when ``address`` is below every symbol this map has.
        """

        index = bisect_right(self._addresses, address) - 1
        if index < 0:
            return None
        symbol = self._by_address[index]
        return symbol, address - symbol.address

    def sections_sorted(self) -> tuple[OutputSection, ...]:
        """Every output section, in ascending VMA order."""

        return tuple(sorted(self.sections, key=lambda item: item.vma))

    def sections_containing(self, address: int) -> tuple[OutputSection, ...]:
        """Return every output section whose extent holds ``address``.

        Smallest first -- the same tie-break `section_containing` picks its
        one answer from -- so ``sections_containing(address)[0] ==
        section_containing(address)`` always.

        This is the honest form of the question `section_containing` only
        answers partially. DKR's ``.assets_lut`` and ``.assets`` share a VMA
        start, and so do the two shapes that address the same thing: a small
        section genuinely *nested* inside a bigger one (``.assets_lut`` is a
        lookup table for exactly the blob ``.assets`` DMAs in) versus an N64
        overlay group, several output sections a cascade script places at one
        shared VMA as mutually exclusive runtime alternatives -- never
        resident together -- because only one is loaded at a time (Banjo-
        Kazooie's ``.CC``/``.GV``/``.MMM``/... and eleven more all start at
        ``0x803863f0``). Both shapes look identical from extents alone: two
        or more sections sharing a start address, ordered smallest first.
        `section_containing` (and `rom_for_vram`/`vram_for_rom`, built on the
        same candidate set) cannot tell them apart and always returns the
        smallest -- correct for the nested case, an arbitrary pick for the
        overlay case. A caller that cares which shape it has needs the whole
        candidate list this method returns, not the one answer.
        """

        candidates = [item for item in self.sections if item.contains(address)]
        return tuple(sorted(candidates, key=lambda item: (item.size, item.vma)))

    def section_containing(self, address: int) -> OutputSection | None:
        """Return the smallest output section whose extent holds ``address``.

        DKR's ``.assets_lut`` and ``.assets`` share a VMA start (the asset
        segments are DMA targets, not both link-time resident at once), so
        more than one output section can legitimately contain the same
        address. The smallest -- the more specific placement -- wins.

        That is the right answer for a section nested inside a bigger one.
        It is not a meaningful answer for an N64 overlay group, where several
        sections share one VMA as alternatives rather than one being "more
        specific" than another -- see `sections_containing` for the honest
        version of this question, which hands back every candidate instead
        of picking one.
        """

        candidates = self.sections_containing(address)
        return candidates[0] if candidates else None

    def input_sections_sorted(self) -> tuple[InputSection, ...]:
        """Every input-section record, in ascending VMA order."""

        return tuple(sorted(self.input_sections, key=lambda item: item.vma))

    def input_section_containing(self, address: int) -> InputSection | None:
        """Return the smallest input-section record whose extent holds ``address``."""

        candidates = [item for item in self.input_sections if item.contains(address)]
        if not candidates:
            return None
        return min(candidates, key=lambda item: (item.size, item.vma))

    def rom_for_vram(self, address: int) -> int | None:
        """Translate a VRAM address to its ROM offset.

        ``None`` when ``address`` falls outside every section that declared
        an explicit ``AT()`` load address -- see the module docstring for
        why a section without one is not assumed to have ROM offset == VRAM
        address.

        When more than one ``AT()``'d section contains ``address`` (see
        `sections_containing`), this resolves through the smallest one, the
        same tie-break `section_containing` uses -- a real answer if that
        section nests inside a bigger one, an arbitrary one if the two are
        siblings in an overlay group. A caller inside a known overlay window
        that needs the *other* candidates' answers should call
        `sections_containing` itself and derive each one's placement by hand
        (``section.load_address + (address - section.vma)``); this method
        only ever returns the smallest section's.
        """

        candidates = [
            item
            for item in self.sections_containing(address)
            if item.load_address is not None
        ]
        if not candidates:
            return None
        section = candidates[0]
        assert section.load_address is not None  # filtered above
        return section.load_address + (address - section.vma)

    def sections_loaded_at(self, offset: int) -> tuple[OutputSection, ...]:
        """Return every output section whose ``AT()`` load range holds ``offset``.

        Smallest first, the ROM-offset mirror of `sections_containing`: the
        same "nested section vs. overlay group" ambiguity applies here, just
        measured against `OutputSection.load_address` instead of `.vma`. A
        zero-size section's load "range" is the single ``offset ==
        load_address`` point, the same convention `OutputSection.contains`
        uses for a zero-size VMA extent.
        """

        candidates = []
        for item in self.sections:
            if item.load_address is None:
                continue
            if item.size == 0:
                if offset == item.load_address:
                    candidates.append(item)
                continue
            if item.load_address <= offset < item.load_address + item.size:
                candidates.append(item)
        return tuple(
            sorted(candidates, key=lambda item: (item.size, item.load_address))
        )

    def vram_for_rom(self, offset: int) -> int | None:
        """Translate a ROM offset to its VRAM address.

        ``None`` when ``offset`` falls outside every section that declared
        an explicit ``AT()`` load address. See `rom_for_vram` for what
        happens when more than one section's load range holds ``offset``:
        the same smallest-wins tie-break, honest for nesting and arbitrary
        for an overlay group -- `sections_loaded_at` hands back every
        candidate for a caller that needs to tell the two apart.
        """

        candidates = self.sections_loaded_at(offset)
        if not candidates:
            return None
        section = candidates[0]
        assert section.load_address is not None  # filtered above
        return section.vma + (offset - section.load_address)


def _merge_wrapped_names(lines: Sequence[str]) -> list[str]:
    """Fold a section name wrapped onto its own line back onto its data.

    ``ld`` prints ``NAME  VMA  SIZE  ...`` as two lines whenever ``NAME``
    alone is too wide for the column: the name by itself, then the rest of
    the record indented to where the name's column would have ended (this
    is common for ``.MIPS.abiflags`` and ``.gnu.attributes`` in a real map).
    Both output-section headers and input-section records wrap this way;
    merging here means the rest of this module never has to know the shape
    happened.
    """

    merged: list[str] = []
    index = 0
    while index < len(lines):
        line = lines[index]
        stripped = line.strip()
        has_continuation = index + 1 < len(lines) and _CONTINUATION_RE.match(
            lines[index + 1]
        )
        if stripped.startswith(".") and " " not in stripped and has_continuation:
            merged.append(line.rstrip() + " " + lines[index + 1].strip())
            index += 2
            continue
        merged.append(line)
        index += 1
    return merged


def parse_ld_map(text: str, *, path: str | None = None) -> LdMap:
    """Parse one GNU ``ld -Map`` file's text into sections, records and symbols.

    Parsing starts after the ``"Linker script and memory map"`` heading when
    the text has one -- a real ``ld -Map`` file always does. Text that has
    no such heading (a handcrafted excerpt in a test, say) is read from the
    top instead, so a synthetic fixture can carry just the lines under test.
    Everything before the heading in a real map -- ``Memory Configuration``,
    ``Discarded input sections`` -- is address-0 placeholder data with no
    bearing on the linked image, and is not parsed.
    """

    lines = _merge_wrapped_names(text.splitlines())
    start = 0
    for index, line in enumerate(lines):
        if line.strip() == _MAP_HEADER:
            start = index + 1
            break

    sections: list[OutputSection] = []
    input_sections: list[InputSection] = []
    symbols: list[LinkerSymbol] = []
    current_output = ""

    for line in lines[start:]:
        stripped = line.strip()
        if not stripped:
            continue

        if not line[:1].isspace() and stripped.startswith("."):
            match = _OUTPUT_SECTION_RE.match(line)
            if match is None:
                continue
            load = match.group("load")
            section = OutputSection(
                name=match.group("name"),
                vma=int(match.group("vma"), 16),
                size=int(match.group("size"), 16),
                load_address=int(load, 16) if load is not None else None,
            )
            sections.append(section)
            current_output = section.name
            continue

        if line[:1].isspace() and stripped.startswith("."):
            match = _INPUT_SECTION_RE.match(line)
            if match is None:
                continue
            input_sections.append(
                InputSection(
                    name=match.group("name"),
                    output_section=current_output,
                    vma=int(match.group("vma"), 16),
                    size=int(match.group("size"), 16),
                    object_path=match.group("path"),
                )
            )
            continue

        if stripped.startswith("0x"):
            match = _SYMBOL_RE.match(line)
            if match is None:
                continue
            address = int(match.group("address"), 16)
            rest = match.group("rest")
            name, separator, expression = rest.partition(" = ")
            if separator:
                if name == ".":
                    # The location counter, not a symbol -- see the module
                    # docstring. Keeping it would collide every alignment
                    # padding in the map under one lookup key.
                    continue
                symbols.append(
                    LinkerSymbol(
                        name=name,
                        address=address,
                        is_assignment=True,
                        expression=expression,
                    )
                )
            elif " " not in rest and "\t" not in rest:
                symbols.append(
                    LinkerSymbol(name=rest, address=address, is_assignment=False)
                )
            # else: an address followed by something that is neither a bare
            # name nor `NAME = expression` -- not a shape this parser
            # understands. Skipped rather than guessed.
            continue

        # `LOAD path` lines, archive-member patterns (`path(.section)`),
        # `FILL mask ...`, `*fill*` padding pseudo-records, and the trailing
        # `OUTPUT(...)` line all fall through to here: none of them places a
        # name at an address, so there is nothing for this reader to record.

    return LdMap(
        path=path,
        sections=tuple(sections),
        input_sections=tuple(input_sections),
        symbols=tuple(symbols),
    )


def read_ld_map(path: str | Path) -> LdMap:
    """Read and parse one ``ld -Map`` file from disk."""

    text = Path(path).read_text(encoding="utf-8", errors="replace")
    return parse_ld_map(text, path=str(path))


@dataclass(frozen=True)
class TilingGap:
    """One place two consecutive input-section extents fail to tile.

    ``gap`` is signed rather than split into two fields plus a sign: positive
    means unclaimed bytes between the two extents (a "gap"), negative means
    the two extents claim the same bytes (an "overlap"). One field lets a
    caller summing an audit's total slack do it without branching on `kind`
    first.
    """

    output_section: str
    low: InputSection
    high: InputSection
    gap: int

    @property
    def kind(self) -> str:
        return "gap" if self.gap > 0 else "overlap"

    def as_dict(self) -> dict[str, Any]:
        return {
            "output_section": self.output_section,
            "kind": self.kind,
            "low_object": self.low.object_path,
            "low_end": self.low.end,
            "high_object": self.high.object_path,
            "high_start": self.high.vma,
            "bytes": abs(self.gap),
        }


def audit_tiling(ldmap: LdMap) -> tuple[TilingGap, ...]:
    """Report every place consecutive input-section extents don't tile.

    Diagnostic data, not a verdict: a gap is sometimes a deliberate ``. =
    ALIGN`` filler (printed by ``ld`` as a separate ``*fill*`` pseudo-record
    this parser does not carry as an input section, so the filled bytes read
    as unclaimed here too) and sometimes a genuine hole, and telling the two
    apart needs more context -- the symbols and section around the gap --
    than this function has. It hands back the coordinates and lets the
    caller decide.

    Zero-size input-section records (a translation unit that contributed
    nothing to a section, e.g. an empty ``.text`` for a hand-asm-only
    object) carry no extent to overlap or gap against, and are excluded from
    the walk entirely.
    """

    by_output: dict[str, list[InputSection]] = {}
    for item in ldmap.input_sections:
        if item.size == 0:
            continue
        by_output.setdefault(item.output_section, []).append(item)

    findings: list[TilingGap] = []
    for output_name, items in by_output.items():
        ordered = sorted(items, key=lambda item: item.vma)
        for low, high in pairwise(ordered):
            delta = high.vma - low.end
            if delta != 0:
                findings.append(
                    TilingGap(output_section=output_name, low=low, high=high, gap=delta)
                )
    findings.sort(key=lambda finding: (finding.output_section, finding.low.vma))
    return tuple(findings)


@dataclass(frozen=True)
class SymbolMovement:
    """One symbol's address in two maps, and the delta between them."""

    name: str
    base_address: int
    shifted_address: int

    @property
    def delta(self) -> int:
        return self.shifted_address - self.base_address

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "base_address": self.base_address,
            "shifted_address": self.shifted_address,
            "delta": self.delta,
        }


@dataclass(frozen=True)
class MovementAudit:
    """Per-shared-symbol placement deltas between a base map and a shifted one."""

    base_path: str | None
    shifted_path: str | None
    allowed_deltas: frozenset[int]
    #: Every symbol both maps define, in the base map's address order.
    movements: tuple[SymbolMovement, ...]
    only_in_base: tuple[str, ...]
    only_in_shifted: tuple[str, ...]

    @property
    def anomalies(self) -> tuple[SymbolMovement, ...]:
        """Shared symbols whose delta is not in `allowed_deltas`.

        The class that must be empty for a shift rehearsal to pass: S0's
        hand audit found none, across ~3,900 shared symbols and two
        independent deltas, on DKR's cascade-scripted shift build.
        """

        return tuple(
            item for item in self.movements if item.delta not in self.allowed_deltas
        )

    @property
    def anomalous_names(self) -> frozenset[str]:
        return frozenset(item.name for item in self.anomalies)

    def as_dict(self) -> dict[str, Any]:
        return {
            "base": self.base_path,
            "shifted": self.shifted_path,
            "allowed_deltas": sorted(self.allowed_deltas),
            "shared_symbols": len(self.movements),
            "only_in_base": list(self.only_in_base),
            "only_in_shifted": list(self.only_in_shifted),
            "anomalies": [item.as_dict() for item in self.anomalies],
        }


def audit_symbol_movement(
    base: LdMap,
    shifted: LdMap,
    *,
    allowed_deltas: Iterable[int] = (0,),
) -> MovementAudit:
    """Compare every symbol two maps share and flag deltas outside `allowed_deltas`.

    This is S0's symbol-movement audit, generalized: relinking the same
    objects against a cascade linker script with an inserted pad must move
    every symbol below the insertion point by exactly 0 and every symbol at
    or above it by exactly the inserted delta -- no third value, either
    delta. Reproducing that (zero anomalies across ~3,900 shared symbols) on
    DKR's ``us.v77`` shift build is this function's own conformance gate.

    `allowed_deltas` defaults to ``{0}`` because two arbitrary maps have no
    shift delta to expect; a caller rehearsing a shift passes the deltas
    under test (S0 used ``{0, 0x10}`` and, separately, ``{0, 0x40}``).
    """

    allowed = frozenset(allowed_deltas)
    base_names = base.symbol_names()
    shifted_names = shifted.symbol_names()

    movements: list[SymbolMovement] = []
    for name in base_names & shifted_names:
        base_symbol = base.symbol(name)
        shifted_symbol = shifted.symbol(name)
        assert (
            base_symbol is not None and shifted_symbol is not None
        )  # from shared names
        movements.append(
            SymbolMovement(
                name=name,
                base_address=base_symbol.address,
                shifted_address=shifted_symbol.address,
            )
        )
    movements.sort(key=lambda item: item.base_address)

    return MovementAudit(
        base_path=base.path,
        shifted_path=shifted.path,
        allowed_deltas=allowed,
        movements=tuple(movements),
        only_in_base=tuple(sorted(base_names - shifted_names)),
        only_in_shifted=tuple(sorted(shifted_names - base_names)),
    )


# ---------------------------------------------------------------------------
# The ELF symbol table (WB-143)
# ---------------------------------------------------------------------------

#: ``st_shndx`` for a symbol the link never resolved to a section.
SHN_UNDEF = 0
#: The first reserved section index. Anything at or above it is a special
#: value rather than an index into the section header table.
SHN_LORESERVE = 0xFF00
#: An absolute symbol: a value, not a place. Every linker-script assignment
#: that survives into the output lands here, which is why this index is the
#: whole point of reading the ELF at all -- see the module docstring.
SHN_ABS = 0xFFF1
#: A common (tentative) definition the link did not allocate.
SHN_COMMON = 0xFFF2

#: ``ELF32_ST_TYPE`` values, named. Reported as the word rather than the
#: number because a report a human reads should not need a table open beside
#: it; unknown values are rendered as ``type-N`` rather than dropped.
ELF_SYMBOL_KINDS: dict[int, str] = {
    0: "notype",
    1: "object",
    2: "func",
    3: "section",
    4: "file",
    5: "common",
    6: "tls",
}

#: ``ELF32_ST_BIND`` values, named, on the same terms.
ELF_SYMBOL_BINDINGS: dict[int, str] = {0: "local", 1: "global", 2: "weak"}

#: Symbol kinds this reader drops. A ``file`` symbol names a translation unit
#: and a ``section`` symbol names a section: neither places a name at an
#: address a project can pin, reference, or shift, and both arrive at value
#: ``0`` in ``SHN_ABS`` (``file``) or duplicate a section start (``section``)
#: where they would only add noise to a name-keyed census.
_ELF_SKIPPED_KINDS = frozenset({"file", "section"})

_ELF_MAGIC = b"\x7fELF"
_ELFCLASS32 = 1
_ELFDATA2MSB = 2
_SHT_SYMTAB = 2
_SHF_ALLOC = 0x2
#: One ``Elf32_Sym`` is 16 bytes: name, value, size, info, other, shndx.
_ELF32_SYM_SIZE = 16


class ElfFormatError(ValueError):
    """The file is not the big-endian 32-bit ELF this reader was written for.

    A subclass of `ValueError` so that every command in the shift family --
    all of which already funnel `ValueError` into one ``error:`` line --
    reports a bad ``--elf`` the same way they report a bad ``--map``, without
    a second except clause per call site.
    """


@dataclass(frozen=True)
class ElfSection:
    """One ELF section header: enough of it to own an address."""

    name: str
    address: int
    size: int
    allocated: bool
    """Whether ``SHF_ALLOC`` is set -- whether this section is really in the
    running image. Debug and symbol-table sections are not, and a symbol
    "owned" by one of them owns no run-time address."""

    @property
    def end(self) -> int:
        return self.address + self.size

    def contains(self, address: int) -> bool:
        if self.size == 0:
            return address == self.address
        return self.address <= address < self.end

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "address": self.address,
            "size": self.size,
            "allocated": self.allocated,
        }


@dataclass(frozen=True)
class ElfSymbol:
    """One ``.symtab`` entry, with the three facts a map cannot print."""

    name: str
    value: int
    size: int
    kind: str
    """One of `ELF_SYMBOL_KINDS`' values, or ``type-N`` for an unknown one."""

    binding: str
    """One of `ELF_SYMBOL_BINDINGS`' values, or ``bind-N``."""

    section_index: int
    section: str | None
    """The owning section's name, or ``None`` when `section_index` is a
    reserved value (`SHN_ABS`, `SHN_UNDEF`, `SHN_COMMON`) and there is no
    section to name."""

    @property
    def is_absolute(self) -> bool:
        return self.section_index == SHN_ABS

    @property
    def is_undefined(self) -> bool:
        return self.section_index == SHN_UNDEF

    @property
    def is_object_backed(self) -> bool:
        """Whether a real output section owns this symbol.

        The property the shift question turns on: an object-backed symbol
        moves when its section moves, by construction, and an absolute one
        cannot.
        """

        return 0 < self.section_index < SHN_LORESERVE

    @property
    def shadows_definition(self) -> bool:
        """Whether this absolute symbol overrode an object's definition.

        The WB-143 rule, and the evidence behind it is `size`. GNU ld lets a
        linker-script assignment win over an object that defines the same
        name -- silently, with no warning -- and emits one ``SHN_ABS`` symbol
        that *keeps the losing definition's* ``st_size`` and ``st_type``. A
        pin that never had an object behind it has nothing to inherit and
        arrives ``notype``, size ``0``.

        Measured on pilotwings64's ``undefined_syms_auto.txt`` (S6 §4.4):
        exactly the ten pins whose deletion ablation B proved byte-identical
        carry a size here, and none of the other twenty-seven does. Zero
        false positives and zero misses against a hand-derived ground truth
        of ten.
        """

        return self.is_absolute and self.size > 0

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "value": self.value,
            "size": self.size,
            "kind": self.kind,
            "binding": self.binding,
            "section": self.section,
        }


@dataclass
class ElfSymbols:
    """One linked ELF's symbol table and the sections its symbols live in.

    Not frozen for the same reason `LdMap` is not: `__post_init__` builds the
    name index once, and a whole-project census asks this thousands of times.
    """

    path: str | None
    sections: tuple[ElfSection, ...]
    symbols: tuple[ElfSymbol, ...]

    def __post_init__(self) -> None:
        by_name: dict[str, ElfSymbol] = {}
        for symbol in self.symbols:
            # Last write wins, the same rule `LdMap` applies and for the same
            # reason: a real symbol table carries repeated local names (pw64's
            # carries 24 `_MACRO_INC_GUARD` rows), and a name-keyed lookup has
            # to answer with one of them rather than refuse.
            by_name[symbol.name] = symbol
        self._by_name: dict[str, ElfSymbol] = by_name

    def symbol(self, name: str) -> ElfSymbol | None:
        return self._by_name.get(name)

    def names(self) -> frozenset[str]:
        return frozenset(self._by_name)

    def section_at(self, address: int) -> ElfSection | None:
        """The smallest allocated section whose extent holds ``address``.

        Smallest-first for the same reason :meth:`LdMap.section_containing`
        picks that way -- and with the same honesty caveat: an N64 overlay
        group places several sections at one address as alternatives, and no
        tie-break makes one of them the right answer.
        """

        candidates = [
            item for item in self.sections if item.allocated and item.contains(address)
        ]
        if not candidates:
            return None
        return min(candidates, key=lambda item: (item.size, item.address))


def parse_elf_symbols(data: bytes, *, path: str | None = None) -> ElfSymbols:
    """Parse one big-endian ELF32's ``.symtab`` into named, typed symbols.

    Refuses anything that is not a big-endian 32-bit ELF rather than reading
    a plausible-looking number out of the wrong offsets -- the same rule
    :func:`~decomp_workbench.shift_audit.require_parsed_map` applies to a
    file handed in as ``--map``. An ELF with no ``.symtab`` (a stripped
    image) is refused too, with the reason named: a stripped link cannot
    answer this command's question and reporting an empty census for it
    would be a confident wrong answer.
    """

    if len(data) < 52 or data[:4] != _ELF_MAGIC:
        raise ElfFormatError(
            f"{path or 'input'} is not an ELF file (bad magic): --elf wants the "
            "linked ELF your `ld` produced, not the image or the map"
        )
    if data[4] != _ELFCLASS32:
        raise ElfFormatError(
            f"{path or 'input'}: only 32-bit ELF (EI_CLASS=1) is supported, "
            f"got class {data[4]}"
        )
    if data[5] != _ELFDATA2MSB:
        raise ElfFormatError(
            f"{path or 'input'}: only big-endian ELF (EI_DATA=2) is supported, "
            f"got data encoding {data[5]}"
        )

    endian = ">"
    (e_shoff,) = struct.unpack_from(endian + "I", data, 0x20)
    e_shentsize, e_shnum, e_shstrndx = struct.unpack_from(endian + "HHH", data, 0x2E)
    if e_shoff == 0 or e_shnum == 0:
        raise ElfFormatError(f"{path or 'input'} carries no section header table")

    def header(index: int) -> tuple[int, int, int, int, int, int, int]:
        offset = e_shoff + index * e_shentsize
        name, kind, flags, address, file_offset, size, link = struct.unpack_from(
            endian + "7I", data, offset
        )
        return name, kind, flags, address, file_offset, size, link

    def string_at(table_offset: int, table_size: int, index: int) -> str:
        start = table_offset + index
        end = data.find(b"\x00", start, table_offset + table_size)
        if end < 0:
            end = table_offset + table_size
        return data[start:end].decode("ascii", errors="replace")

    _, _, _, _, shstr_offset, shstr_size, _ = header(e_shstrndx)
    sections: list[ElfSection] = []
    symtab: tuple[int, int, int] | None = None
    for index in range(e_shnum):
        name, kind, flags, address, file_offset, size, link = header(index)
        sections.append(
            ElfSection(
                name=string_at(shstr_offset, shstr_size, name),
                address=address,
                size=size,
                allocated=bool(flags & _SHF_ALLOC),
            )
        )
        if kind == _SHT_SYMTAB and symtab is None:
            symtab = (file_offset, size, link)

    if symtab is None:
        raise ElfFormatError(
            f"{path or 'input'} carries no .symtab: this ELF is stripped, and a "
            "stripped link cannot answer which of its symbols are absolute"
        )

    sym_offset, sym_size, str_index = symtab
    _, _, _, _, str_offset, str_size, _ = header(str_index)
    symbols: list[ElfSymbol] = []
    for index in range(sym_size // _ELF32_SYM_SIZE):
        offset = sym_offset + index * _ELF32_SYM_SIZE
        st_name, st_value, st_size, st_info, _st_other, st_shndx = struct.unpack_from(
            endian + "IIIBBH", data, offset
        )
        symbol_name = string_at(str_offset, str_size, st_name)
        if not symbol_name:
            continue
        symbol_kind = ELF_SYMBOL_KINDS.get(st_info & 0xF, f"type-{st_info & 0xF}")
        if symbol_kind in _ELF_SKIPPED_KINDS:
            continue
        owner = (
            sections[st_shndx].name
            if 0 < st_shndx < SHN_LORESERVE and st_shndx < len(sections)
            else None
        )
        symbols.append(
            ElfSymbol(
                name=symbol_name,
                value=st_value,
                size=st_size,
                kind=symbol_kind,
                binding=ELF_SYMBOL_BINDINGS.get(st_info >> 4, f"bind-{st_info >> 4}"),
                section_index=st_shndx,
                section=owner,
            )
        )
    return ElfSymbols(path=path, sections=tuple(sections), symbols=tuple(symbols))


def read_elf_symbols(path: str | Path) -> ElfSymbols:
    """Read and parse one linked ELF's symbol table from disk."""

    return parse_elf_symbols(Path(path).read_bytes(), path=str(path))
