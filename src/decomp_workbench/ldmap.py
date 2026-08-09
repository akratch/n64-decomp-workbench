"""Read a GNU ``ld -Map`` file into addressable sections, records, and symbols.

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
"""

from __future__ import annotations

import re
from bisect import bisect_right
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from itertools import pairwise
from pathlib import Path
from typing import Any

__all__ = [
    "InputSection",
    "LdMap",
    "LinkerSymbol",
    "MovementAudit",
    "OutputSection",
    "SymbolMovement",
    "TilingGap",
    "audit_symbol_movement",
    "audit_tiling",
    "parse_ld_map",
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

    def section_containing(self, address: int) -> OutputSection | None:
        """Return the smallest output section whose extent holds ``address``.

        DKR's ``.assets_lut`` and ``.assets`` share a VMA start (the asset
        segments are DMA targets, not both link-time resident at once), so
        more than one output section can legitimately contain the same
        address. The smallest -- the more specific placement -- wins.
        """

        candidates = [item for item in self.sections if item.contains(address)]
        if not candidates:
            return None
        return min(candidates, key=lambda item: (item.size, item.vma))

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
        """

        candidates = [
            item
            for item in self.sections
            if item.load_address is not None and item.contains(address)
        ]
        if not candidates:
            return None
        section = min(candidates, key=lambda item: (item.size, item.vma))
        assert section.load_address is not None  # filtered above
        return section.load_address + (address - section.vma)

    def vram_for_rom(self, offset: int) -> int | None:
        """Translate a ROM offset to its VRAM address.

        ``None`` when ``offset`` falls outside every section that declared
        an explicit ``AT()`` load address.
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
        if not candidates:
            return None
        section = min(candidates, key=lambda item: (item.size, item.load_address))
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
