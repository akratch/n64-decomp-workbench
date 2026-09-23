"""Audit a module's objects for the two promotion faults no score can see.

A function can be byte-exact in its own object and still break the final
image, in two ways that both surfaced on one promotion (Mickey's Speedway
USA, 2026-09-16, a 14 KiB overlay function scored exact):

1. **A bare cross-module name.** In a module that ships unrelocated, every
   reference out of the module stores an *addend*, so it must be spelled with
   a placeholder whose value the relocation surface supplies. A reference
   spelled with the other module's *own* name -- a resident data symbol, say
   -- gets a value line under that name, and a linker symbol assignment is
   global: it silently redefines the resident symbol for every other object
   in the link. Three data names did that and moved 95 resident bytes. The
   function's calls had been rebound; its *data* references had not, because
   the habit was learned on calls.
2. **A jump-table pool the image already ships.** A ``switch`` compiled into
   the object carries its table in the object's read-only data. If the host
   has not arranged for that section to *be* the shipped table -- placed at
   the shipped range, or externalized -- the link emits a second copy, and
   everything after it shifts. A 13-entry table did that to every later
   overlay while the function itself was exact.

Both are visible in the objects before anything links, which is what this
audit reads. It is the same object set and module map ``reloc-surface``
takes, plus two optional facts only the host has: the names the *other* side
of the link defines (``resident``), and the spelling the host reserves for a
placeholder (``surface_pattern``). Nothing here is specific to one game:
"resident" means "defined outside this module", whatever the project calls
it.

Nothing builds or links. A refusal names the object, the symbol or table,
and the form the host must use instead.
"""

from __future__ import annotations

import re
import struct
from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .elf import SHN_UNDEF, ElfFormatError, ElfObject, parse_elf, r_mips_name
from .reloc_surface import (
    ASSIGNMENT_RE,
    LINKABLE_BINDINGS,
    R_MIPS_26,
    R_MIPS_32,
    R_MIPS_HI16,
    R_MIPS_LO16,
    ModuleMap,
    parse_linker_block,
    sext16,
)

AUDIT_SCHEMA = "decomp-workbench-promotion-audit-v1"

STT_FUNC = 2
STT_SECTION = 3
STT_FILE = 4

#: Reference kinds. A call is a function reached by ``jal``; anything else --
#: a ``%hi``/``%lo`` pair, a pointer word -- is data, and data is the half a
#: habit learned on calls misses.
KIND_CALL = "call"
KIND_DATA = "data"
KIND_MIXED = "call+data"

#: Reference verdicts.
REF_RESIDENT_OVERRIDE = "resident-override"
REF_BARE = "bare"
REF_SURFACE = "surface"
REF_UNCLASSIFIED = "unclassified"

#: Pool verdicts.
POOL_DUPLICATE = "duplicates-shipped-pool"
POOL_PLACED = "placed"
POOL_PLACED_DISAGREES = "placed-disagrees"

REFUSING_REFERENCES = frozenset({REF_RESIDENT_OVERRIDE, REF_BARE})
REFUSING_POOLS = frozenset({POOL_DUPLICATE, POOL_PLACED_DISAGREES})

RODATA_PREFIXES = (".rodata", ".rdata")


def _is_text(name: str) -> bool:
    return name.startswith(".text")


def _is_rodata(name: str) -> bool:
    return name.startswith(RODATA_PREFIXES)


# ---------------------------------------------------------------------------
# Resident names
# ---------------------------------------------------------------------------


def resident_names_from_elf(elf: ElfObject) -> set[str]:
    """Every linkable name an object or linked ELF defines."""

    return {
        symbol.name
        for symbol in elf.symbols
        if symbol.name
        and symbol.shndx != SHN_UNDEF
        and symbol.bind in LINKABLE_BINDINGS
        and symbol.type not in (STT_SECTION, STT_FILE)
    }


_IDENTIFIER = re.compile(r"^[A-Za-z_.$][A-Za-z0-9_.$]*$")


def resident_names_from_text(text: str) -> set[str]:
    """Names from a symbol list: one per line, or ``name = value;`` lines.

    Both are what a project already has -- a splat-style symbol address file
    is the second shape, a hand list the first. Comments (``//``, ``#``,
    ``/* */`` lines) are skipped; a line whose first token is not an
    identifier is ignored rather than guessed at.
    """

    names: set[str] = set()
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith(("//", "#", "/*", "*")):
            continue
        match = ASSIGNMENT_RE.match(stripped)
        token = match.group("name") if match else stripped.split()[0]
        if _IDENTIFIER.match(token):
            names.add(token)
    return names


def load_resident_names(paths: Iterable[str | Path]) -> set[str]:
    """Read resident names from ELF files or symbol lists, by content."""

    names: set[str] = set()
    for raw in paths:
        path = Path(raw).expanduser()
        data = path.read_bytes()
        if data.startswith(b"\x7fELF"):
            try:
                names |= resident_names_from_elf(parse_elf(data, path=str(path)))
            except ElfFormatError as error:
                raise ValueError(f"{path}: {error}") from error
        else:
            names |= resident_names_from_text(data.decode("utf-8", errors="replace"))
    return names


# ---------------------------------------------------------------------------
# Findings
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ReferenceSite:
    object: str
    section: str
    offset: int
    type: int

    def as_dict(self) -> dict[str, Any]:
        return {
            "object": self.object,
            "section": self.section,
            "offset": self.offset,
            "type": self.type,
            "kind": r_mips_name(self.type),
        }


@dataclass(frozen=True)
class ExternalReference:
    """One name the module references and does not define."""

    name: str
    kind: str
    verdict: str
    sites: tuple[ReferenceSite, ...]
    block_value: str | None = None

    @property
    def refused(self) -> bool:
        return self.verdict in REFUSING_REFERENCES

    @property
    def message(self) -> str:
        objects = sorted({site.object for site in self.sites})
        where = ", ".join(objects)
        if self.verdict == REF_RESIDENT_OVERRIDE:
            line = (
                f" The linker block already assigns it ({self.name} = "
                f"{self.block_value};)."
                if self.block_value is not None
                else ""
            )
            return (
                f"{where}: {self.kind} reference to {self.name}, which the "
                "other side of the link defines. Any value line for this name "
                "is a global assignment that redefines it for every object, "
                "so the shipped addend overrides the real definition; spell "
                "the reference with the host's placeholder (rebind) form "
                "instead." + line
            )
        if self.verdict == REF_BARE:
            return (
                f"{where}: {self.kind} reference to {self.name} does not use "
                "the declared placeholder spelling; rebind it before linking"
            )
        if self.verdict == REF_SURFACE:
            return f"{where}: {self.kind} reference through placeholder {self.name}"
        return (
            f"{where}: {self.kind} reference to {self.name}; nothing declared "
            "whether this name is a placeholder or another module's own"
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "kind": self.kind,
            "verdict": self.verdict,
            "refused": self.refused,
            "block_value": self.block_value,
            "sites": [site.as_dict() for site in self.sites],
            "message": self.message,
        }


@dataclass(frozen=True)
class TableReference:
    function: str | None
    offset: int

    def as_dict(self) -> dict[str, Any]:
        return {"function": self.function, "offset": self.offset}


@dataclass(frozen=True)
class JumpTable:
    """One run of text-relative pointer words in an object's read-only data."""

    object: str
    section: str
    offset: int
    entries: int
    verdict: str
    referenced_by: tuple[TableReference, ...] = ()
    placement_offset: int | None = None
    agree: int | None = None
    disagree: int | None = None

    @property
    def size(self) -> int:
        return self.entries * 4

    @property
    def refused(self) -> bool:
        return self.verdict in REFUSING_POOLS

    @property
    def message(self) -> str:
        users = ", ".join(
            item.function or f"text+0x{item.offset:X}" for item in self.referenced_by
        ) or ("no function found loading it")
        head = (
            f"{self.object}: {self.entries}-entry jump table at "
            f"{self.section}+0x{self.offset:X} (used by {users})"
        )
        if self.verdict == POOL_DUPLICATE:
            return (
                head + f": the module map places no {self.section} for this "
                f"object, so the link emits these {self.size} bytes beside the "
                "shipped pool and shifts everything after it. Externalize the "
                "table (the shipped pool supplies it) or place this section at "
                "the shipped range in the module map"
            )
        if self.verdict == POOL_PLACED_DISAGREES:
            return (
                head + f": placed at module offset 0x{self.placement_offset:X}, "
                f"but {self.disagree} of {self.entries} entries disagree with the "
                "shipped words there; the placement or the table is wrong"
            )
        corroboration = (
            f"; {self.agree}/{self.entries} entries agree with the image"
            if self.agree is not None
            else ""
        )
        return head + ": placed by the module map" + corroboration

    def as_dict(self) -> dict[str, Any]:
        return {
            "object": self.object,
            "section": self.section,
            "offset": self.offset,
            "entries": self.entries,
            "size": self.size,
            "verdict": self.verdict,
            "refused": self.refused,
            "referenced_by": [item.as_dict() for item in self.referenced_by],
            "placement_offset": self.placement_offset,
            "agree": self.agree,
            "disagree": self.disagree,
            "message": self.message,
        }


@dataclass(frozen=True)
class BlockOverride:
    """A linker-block assignment to a name the other side of the link defines."""

    name: str
    value: str

    @property
    def message(self) -> str:
        return (
            f"the linker block assigns {self.name} = {self.value};, and the "
            "other side of the link defines that name: the assignment "
            "overrides the definition for every object"
        )

    def as_dict(self) -> dict[str, Any]:
        return {"name": self.name, "value": self.value, "message": self.message}


@dataclass(frozen=True)
class PromotionAudit:
    module: str
    objects: tuple[str, ...]
    references: tuple[ExternalReference, ...]
    tables: tuple[JumpTable, ...]
    block_overrides: tuple[BlockOverride, ...] = ()
    unplaced_rodata: tuple[dict[str, Any], ...] = ()
    resident_declared: bool = False
    surface_pattern: str | None = None
    image_read: bool = False
    warnings: tuple[str, ...] = field(default=())

    @property
    def refusals(self) -> list[str]:
        return [
            *(item.message for item in self.references if item.refused),
            *(item.message for item in self.tables if item.refused),
            *(item.message for item in self.block_overrides),
        ]

    @property
    def passed(self) -> bool:
        return not self.refusals

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": AUDIT_SCHEMA,
            "module": self.module,
            "objects": list(self.objects),
            "pass": self.passed,
            "refusal_count": len(self.refusals),
            "refusals": self.refusals,
            "references": [item.as_dict() for item in self.references],
            "jump_tables": [item.as_dict() for item in self.tables],
            "block_overrides": [item.as_dict() for item in self.block_overrides],
            "unplaced_rodata": [dict(item) for item in self.unplaced_rodata],
            "resident_declared": self.resident_declared,
            "surface_pattern": self.surface_pattern,
            "image_read": self.image_read,
            "warnings": list(self.warnings),
        }


# ---------------------------------------------------------------------------
# The audit
# ---------------------------------------------------------------------------


def _module_defined(objects: Sequence[tuple[str, ElfObject]]) -> set[str]:
    out: set[str] = set()
    for _name, elf in objects:
        for symbol in elf.symbols:
            if (
                symbol.name
                and symbol.shndx != SHN_UNDEF
                and symbol.bind in LINKABLE_BINDINGS
            ):
                out.add(symbol.name)
    return out


def _section_name(elf: ElfObject, index: int) -> str | None:
    for section in elf.sections:
        if section.index == index:
            return section.name
    return None


def _word(data: bytes, offset: int) -> int | None:
    if offset < 0 or offset + 4 > len(data):
        return None
    return int(struct.unpack_from(">I", data, offset)[0])


def _external_references(
    objects: Sequence[tuple[str, ElfObject]],
    *,
    resident: set[str] | None,
    pattern: re.Pattern[str] | None,
    block: Mapping[str, str],
) -> list[ExternalReference]:
    local = _module_defined(objects)
    sites: dict[str, list[ReferenceSite]] = defaultdict(list)
    for object_name, elf in objects:
        for section_name, relocations in elf.relocations.items():
            for reloc in relocations:
                symbol = elf.symbol(reloc.sym_index)
                if symbol is None or not symbol.name or symbol.shndx != SHN_UNDEF:
                    continue
                if symbol.name in local:
                    continue
                sites[symbol.name].append(
                    ReferenceSite(
                        object=object_name,
                        section=section_name,
                        offset=reloc.offset,
                        type=reloc.type,
                    )
                )
    out = []
    for name in sorted(sites):
        types = {site.type for site in sites[name]}
        kind = (
            KIND_CALL
            if types == {R_MIPS_26}
            else KIND_MIXED
            if R_MIPS_26 in types
            else KIND_DATA
        )
        if resident is not None and name in resident:
            verdict = REF_RESIDENT_OVERRIDE
        elif pattern is not None:
            verdict = REF_SURFACE if pattern.search(name) else REF_BARE
        else:
            verdict = REF_UNCLASSIFIED
        out.append(
            ExternalReference(
                name=name,
                kind=kind,
                verdict=verdict,
                sites=tuple(sites[name]),
                block_value=block.get(name),
            )
        )
    return out


def _section_loads(
    elf: ElfObject, section_index: int
) -> dict[int, tuple[TableReference, ...]]:
    """Every offset of one section that a ``%hi``/``%lo`` pair in text loads.

    The addend is REL-style, read from the instruction words themselves, and
    the pair is matched the way the linker matches it: an ``R_MIPS_LO16``
    closes the ``R_MIPS_HI16`` records before it against the same symbol, and
    a further ``R_MIPS_LO16`` reuses the last high half. A static function
    with no symbol of its own is reported by offset alone, never attributed
    to a neighbour.
    """

    functions: list[tuple[str, str, int, int]] = []
    for symbol in elf.symbols:
        if symbol.type != STT_FUNC or symbol.shndx == SHN_UNDEF:
            continue
        owner = _section_name(elf, symbol.shndx)
        if owner is not None:
            functions.append((owner, symbol.name, symbol.value, symbol.size))

    def containing(section: str, offset: int) -> str | None:
        for owner, name, start, size in functions:
            if owner == section and start <= offset < start + max(size, 1):
                return name
        return None

    found: dict[int, dict[int, TableReference]] = defaultdict(dict)
    for section_name, relocations in elf.relocations.items():
        if not _is_text(section_name):
            continue
        text = elf.section_bytes(section_name) or b""
        pending: dict[int, list[int]] = defaultdict(list)
        last_high: dict[int, int] = {}
        for reloc in relocations:
            loaded = elf.symbol(reloc.sym_index)
            if loaded is None or loaded.shndx != section_index:
                continue
            base = 0 if loaded.type == STT_SECTION else loaded.value
            word = _word(text, reloc.offset)
            if word is None:
                continue
            if reloc.type == R_MIPS_HI16:
                pending[reloc.sym_index].append(word & 0xFFFF)
            elif reloc.type == R_MIPS_LO16:
                highs = pending.pop(reloc.sym_index, [])
                if highs:
                    last_high[reloc.sym_index] = highs[-1]
                else:
                    highs = [last_high.get(reloc.sym_index, 0)]
                low = sext16(word & 0xFFFF)
                for high in highs:
                    target = ((high << 16) + low + base) & 0xFFFFFFFF
                    found[target][reloc.offset] = TableReference(
                        function=containing(section_name, reloc.offset),
                        offset=reloc.offset,
                    )
    return {
        target: tuple(users[key] for key in sorted(users))
        for target, users in found.items()
    }


def _jump_tables(
    object_name: str,
    elf: ElfObject,
    module: ModuleMap,
    image: bytes | None,
) -> tuple[list[JumpTable], list[dict[str, Any]], list[str]]:
    tables: list[JumpTable] = []
    unplaced: list[dict[str, Any]] = []
    warnings: list[str] = []
    placements = module.placements_for(object_name)
    for section in elf.sections:
        if not _is_rodata(section.name) or section.size == 0:
            continue
        placed = next((p for p in placements if p.section == section.name), None)
        data = elf.section_bytes(section.name) or b""
        entries: list[tuple[int, int, int]] = []
        for reloc in elf.relocations_for(section.name):
            if reloc.type != R_MIPS_32:
                continue
            symbol = elf.symbol(reloc.sym_index)
            if symbol is None or symbol.shndx == SHN_UNDEF or symbol.type == STT_FUNC:
                continue
            target_section = _section_name(elf, symbol.shndx)
            if target_section is None or not _is_text(target_section):
                continue
            stored = _word(data, reloc.offset)
            if stored is None:
                continue
            base = 0 if symbol.type == STT_SECTION else symbol.value
            entries.append((reloc.offset, symbol.shndx, (base + stored) & 0xFFFFFFFF))
        entries.sort()
        # Two switches' tables sit back to back in one section, so contiguity
        # alone would read them as one table. A table starts where code loads
        # it; a run is split at every offset some %hi/%lo pair addresses.
        loads = _section_loads(elf, section.index)
        runs: list[list[tuple[int, int, int]]] = []
        for entry in entries:
            if runs and entry[0] == runs[-1][-1][0] + 4 and entry[0] not in loads:
                runs[-1].append(entry)
            else:
                runs.append([entry])
        covered = 0
        for run in runs:
            start = run[0][0]
            covered += 4 * len(run)
            users = loads.get(start, ())
            if placed is None:
                tables.append(
                    JumpTable(
                        object=object_name,
                        section=section.name,
                        offset=start,
                        entries=len(run),
                        verdict=POOL_DUPLICATE,
                        referenced_by=users,
                    )
                )
                continue
            agree = disagree = None
            text_placement = next(
                (p for p in placements if p.section == _section_name(elf, run[0][1])),
                None,
            )
            if image is not None and text_placement is not None:
                agree = disagree = 0
                for offset, _index, target in run:
                    shipped = _word(image, module.image_offset(placed.offset + offset))
                    expected = (
                        module.synthetic_vma + text_placement.offset + target
                    ) & 0xFFFFFFFF
                    if shipped == expected:
                        agree += 1
                    else:
                        disagree += 1
            elif image is not None:
                warnings.append(
                    f"{object_name}: the jump table at {section.name}+0x{start:X} "
                    "targets a text section the module map does not place; its "
                    "entries cannot be read against the image"
                )
            tables.append(
                JumpTable(
                    object=object_name,
                    section=section.name,
                    offset=start,
                    entries=len(run),
                    verdict=POOL_PLACED_DISAGREES if disagree else POOL_PLACED,
                    referenced_by=users,
                    placement_offset=placed.offset,
                    agree=agree,
                    disagree=disagree,
                )
            )
        if placed is None and section.size > covered:
            unplaced.append(
                {
                    "object": object_name,
                    "section": section.name,
                    "size": section.size,
                    "jump_table_bytes": covered,
                    "message": (
                        f"{object_name}: {section.name} carries "
                        f"{section.size - covered} byte(s) outside any jump "
                        "table and the module map places no copy of it; if "
                        "the image already ships these constants the link "
                        "duplicates them"
                    ),
                }
            )
    return tables, unplaced, warnings


def promotion_audit(
    objects: Sequence[tuple[str, ElfObject]],
    module: ModuleMap,
    *,
    resident: set[str] | None = None,
    surface_pattern: str | None = None,
    linker_block: str | None = None,
    image: bytes | None = None,
) -> PromotionAudit:
    """Audit the objects a module link consumes for the two silent faults.

    ``resident`` is the set of names the other side of the link defines;
    ``surface_pattern`` a regular expression matching the host's placeholder
    spelling; ``linker_block`` the symbol block the link will include (the
    ``reloc-surface`` output or its hand-written predecessor); ``image`` the
    target image, which lets a placed jump table be read against the shipped
    words. Each is optional, and the report says which were missing.
    """

    pattern = re.compile(surface_pattern) if surface_pattern else None
    block = parse_linker_block(linker_block) if linker_block is not None else {}
    references = _external_references(
        objects, resident=resident, pattern=pattern, block=block
    )
    tables: list[JumpTable] = []
    unplaced: list[dict[str, Any]] = []
    warnings: list[str] = []
    for name, elf in objects:
        found, rodata, notes = _jump_tables(name, elf, module, image)
        tables.extend(found)
        unplaced.extend(rodata)
        warnings.extend(notes)
    overrides = (
        tuple(
            BlockOverride(name=name, value=value)
            for name, value in sorted(block.items())
            if name in resident
        )
        if resident is not None
        else ()
    )
    if resident is None:
        warnings.append(
            "no --resident names were supplied, so a reference that redefines "
            "another module's own symbol cannot be told from a placeholder"
        )
    if pattern is None and resident is None:
        warnings.append(
            "no --surface-pattern was declared either; every external "
            "reference is listed as unclassified rather than judged"
        )
    unclassified = [item for item in references if item.verdict == REF_UNCLASSIFIED]
    if unclassified and pattern is None and resident is not None:
        warnings.append(
            f"{len(unclassified)} external reference(s) are neither resident "
            "names nor checked against a placeholder spelling"
        )
    return PromotionAudit(
        module=module.name,
        objects=tuple(name for name, _elf in objects),
        references=tuple(references),
        tables=tuple(tables),
        block_overrides=overrides,
        unplaced_rodata=tuple(unplaced),
        resident_declared=resident is not None,
        surface_pattern=surface_pattern,
        image_read=image is not None,
        warnings=tuple(warnings),
    )


def render(audit: PromotionAudit, *, verbose: bool = False) -> list[str]:
    """The terminal report: refusals first, then what was checked."""

    lines = [
        f"promotion audit {audit.module}: "
        + ("PASS" if audit.passed else f"REFUSED ({len(audit.refusals)})"),
        f"  objects         {len(audit.objects)}",
        f"  external refs   {len(audit.references)} "
        f"({sum(1 for item in audit.references if item.kind != KIND_CALL)} data)",
        f"  jump tables     {len(audit.tables)}",
    ]
    for message in audit.refusals:
        lines.append(f"refused: {message}")
    for item in audit.unplaced_rodata:
        lines.append(f"warning: {item['message']}")
    for message in audit.warnings:
        lines.append(f"warning: {message}")
    if verbose:
        for reference in audit.references:
            if not reference.refused:
                lines.append(f"  {reference.verdict:<13} {reference.message}")
        for table in audit.tables:
            if not table.refused:
                lines.append(f"  {table.verdict:<13} {table.message}")
    return lines


__all__ = [
    "AUDIT_SCHEMA",
    "BlockOverride",
    "ExternalReference",
    "JumpTable",
    "PromotionAudit",
    "load_resident_names",
    "promotion_audit",
    "render",
    "resident_names_from_elf",
    "resident_names_from_text",
]
