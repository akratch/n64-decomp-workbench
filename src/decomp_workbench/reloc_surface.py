"""Synthesize a module's relocation surface from the shipped image.

Some projects ship a code module **unrelocated**: the game's own runtime
linker patches every site named by the module's relocation table after the
module is loaded. What the shipped image stores at such a site is therefore
not a final address but the record's **stored addend** -- the value the
runtime adds a base to.

A C translation unit compiled for such a module cannot express that. The
compiler emits an ordinary ``R_MIPS_26`` or ``R_MIPS_HI16``/``R_MIPS_LO16``
reference to a symbol that has no address in this build, because the symbol
lives in another module or in a section the runtime places. The usual answer
is a placeholder extern whose *value* is supplied as a linker-script
assignment, so that the linked instruction word carries exactly the addend
the shipped image carries.

This module's claim is that **the value is not a judgement call**. For a
candidate whose instruction schedule already agrees with the target at the
site, every placeholder's value is readable from the image at the offset the
relocation names:

===================================  =========================================
relocation                           required symbol value
===================================  =========================================
``R_MIPS_26``                        ``(vma & 0xF0000000) | (stored_imm26 << 2)``
``R_MIPS_HI16`` + ``R_MIPS_LO16``    ``(stored_hi << 16) + sext16(stored_lo)``
``R_MIPS_32``                        ``stored_word``
===================================  =========================================

minus whatever addend the object's own instruction already carries.
Subtracting the object's addend is what lets one base symbol serve many
struct-field references: the compiler puts the field offset in the
instruction, so only the base belongs in the linker script.

Everything here is a pure function over an :class:`~decomp_workbench.elf.
ElfObject`, a :class:`ModuleMap` the host writes once, and the image bytes.
Nothing builds, links, or shells out; the host drives its own build.

The precondition is stated and enforced, not assumed: where two sites for one
symbol demand different values the schedule has diverged *at the site*, no
consistent addend exists, and :func:`synthesize` refuses that symbol and names
the conflicting sites rather than inventing a value.
"""

from __future__ import annotations

import re
import struct
from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from .elf import (
    SHN_UNDEF,
    ElfObject,
    Reloc,
    r_mips_name,
)

SURFACE_SCHEMA = "decomp-workbench-reloc-surface-v1"
MODULE_MAP_SCHEMA = "decomp-workbench-module-map-v1"

R_MIPS_32 = 2
R_MIPS_26 = 4
R_MIPS_HI16 = 5
R_MIPS_LO16 = 6

#: The relocation types whose stored field this module knows how to read. Any
#: other type at a placed site is reported as an unsupported site rather than
#: guessed at -- an unread relocation is exactly how a wrong symbol value gets
#: into a linker script.
SUPPORTED_TYPES = frozenset({R_MIPS_32, R_MIPS_26, R_MIPS_HI16, R_MIPS_LO16})

STB_GLOBAL = 1
STB_WEAK = 2
STT_FUNC = 2

#: The bindings a definition in another object of the module can satisfy a
#: reference with. A `STB_LOCAL` definition resolves nothing outside its own
#: object, so it is not one.
LINKABLE_BINDINGS = frozenset({STB_GLOBAL, STB_WEAK})

#: `NAME = 0x1234;` or `NAME = other_name;` -- the two line shapes a linker
#: symbol block has, and the two this module both writes and reads back.
ASSIGNMENT_RE = re.compile(
    r"^\s*(?P<name>[A-Za-z_][A-Za-z0-9_]*)\s*=\s*(?P<value>[^;]+?)\s*;"
)


class ModuleMapError(ValueError):
    """The module section map is missing, malformed, or self-inconsistent."""


# ---------------------------------------------------------------------------
# The module section map
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SectionRange:
    """One module section, as a module-relative range."""

    name: str
    offset: int
    size: int

    @property
    def end(self) -> int:
        return self.offset + self.size

    def contains(self, module_offset: int, width: int = 1) -> bool:
        return self.offset <= module_offset and module_offset + width <= self.end

    def as_dict(self) -> dict[str, Any]:
        return {"name": self.name, "offset": self.offset, "size": self.size}


@dataclass(frozen=True)
class Placement:
    """Where one object's section sits inside the module.

    ``offset`` is module-relative, the same coordinate the section ranges and
    the relocation-table sites use, so a site's module offset is
    ``placement.offset + reloc.offset`` and needs no linked ELF. The link is
    exactly what is missing when a promotion fails to resolve, so a map that
    required one would be useless in the only case that matters.
    """

    object: str
    section: str
    offset: int
    size: int | None = None

    @property
    def end(self) -> int | None:
        return None if self.size is None else self.offset + self.size

    def as_dict(self) -> dict[str, Any]:
        return {
            "object": self.object,
            "section": self.section,
            "offset": self.offset,
            "size": self.size,
        }


@dataclass(frozen=True)
class TableSite:
    """One entry of the module's own shipped relocation table.

    A site the table does not name is *not* a relocation site in the shipped
    image: reading an addend there reads an ordinary instruction word. The
    table is optional -- a host that cannot decode it gets the whole surface
    with no corroboration, and :attr:`RelocSurface.corroborated` says so.
    """

    offset: int
    type: int | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "offset": self.offset,
            "type": self.type,
            "kind": None if self.type is None else r_mips_name(self.type),
        }


@dataclass(frozen=True)
class ModuleMap:
    """Everything about the module's placement the synthesis needs.

    Written once per module by the host, from whatever it already knows: a
    splat/atlas configuration, a linker map, or the module header itself.
    """

    name: str
    image_start: int
    image_end: int
    synthetic_vma: int = 0
    sections: tuple[SectionRange, ...] = ()
    placements: tuple[Placement, ...] = ()
    table_sites: tuple[TableSite, ...] = ()
    alias_template: str | None = None

    def section(self, name: str) -> SectionRange | None:
        for item in self.sections:
            if item.name == name:
                return item
        return None

    def placements_for(self, object_name: str) -> tuple[Placement, ...]:
        """Return the placements matching ``object_name`` by path or basename.

        Either separator, because the map is written once by the host and the
        objects are named by the build; nothing makes the two agree on which
        slash they use, and matching only on ``/`` places nothing at all on a
        Windows host and emits an empty surface for it.
        """

        base = _basename(object_name)
        return tuple(
            item
            for item in self.placements
            if item.object == object_name or _basename(item.object) == base
        )

    def image_offset(self, module_offset: int) -> int:
        return self.image_start + module_offset

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "image_start": self.image_start,
            "image_end": self.image_end,
            "synthetic_vma": self.synthetic_vma,
            "sections": [item.as_dict() for item in self.sections],
            "placements": [item.as_dict() for item in self.placements],
            "table_sites": len(self.table_sites),
            "alias_template": self.alias_template,
        }


def _basename(path: str) -> str:
    """The last component of ``path`` under either separator."""

    return path.replace("\\", "/").rsplit("/", 1)[-1]


def _integer(value: Any, *, where: str) -> int:
    """Accept ``0x1234``, ``"0x1234"``, or a decimal in either spelling."""

    if isinstance(value, bool):
        raise ModuleMapError(f"{where}: expected an integer, not a boolean")
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        text = value.strip()
        try:
            return int(text, 0)
        except ValueError as error:
            raise ModuleMapError(f"{where}: {value!r} is not an integer") from error
    raise ModuleMapError(f"{where}: expected an integer, got {type(value).__name__}")


def _mapping(value: Any, *, where: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ModuleMapError(f"{where}: expected a JSON object")
    return value


def parse_module_map(payload: Any, *, origin: str = "module map") -> ModuleMap:
    """Build a :class:`ModuleMap` from the host's JSON document.

    Refuses rather than guesses: an unknown schema, a section outside the
    module, or a placement outside its section are all reported here, because
    every one of them silently produces plausible-looking wrong addends.
    """

    document = _mapping(payload, where=origin)
    schema = document.get("schema")
    if schema is not None and schema != MODULE_MAP_SCHEMA:
        raise ModuleMapError(
            f"{origin}: unknown schema {schema!r}; expected {MODULE_MAP_SCHEMA!r}"
        )
    body = _mapping(document.get("module", document), where=f"{origin}: module")

    for required in ("image_start", "image_end"):
        if required not in body:
            raise ModuleMapError(f"{origin}: module is missing {required!r}")
    image_start = _integer(body["image_start"], where=f"{origin}: image_start")
    image_end = _integer(body["image_end"], where=f"{origin}: image_end")
    if image_end <= image_start:
        raise ModuleMapError(
            f"{origin}: image_end (0x{image_end:x}) must be past "
            f"image_start (0x{image_start:x})"
        )
    span = image_end - image_start

    sections: list[SectionRange] = []
    raw_sections = body.get("sections", {})
    if isinstance(raw_sections, Mapping):
        items: Iterable[tuple[str, Any]] = raw_sections.items()
    elif isinstance(raw_sections, Sequence) and not isinstance(
        raw_sections, str | bytes
    ):
        items = [
            (str(_mapping(entry, where=f"{origin}: sections").get("name", "")), entry)
            for entry in raw_sections
        ]
    else:
        raise ModuleMapError(f"{origin}: sections must be an object or a list")
    for name, entry in items:
        where = f"{origin}: section {name!r}"
        record = _mapping(entry, where=where)
        offset = _integer(record.get("offset", 0), where=f"{where} offset")
        size = _integer(record.get("size", 0), where=f"{where} size")
        if not name:
            raise ModuleMapError(f"{origin}: every section needs a name")
        if offset < 0 or size < 0:
            raise ModuleMapError(f"{where}: negative offset or size")
        if offset + size > span:
            raise ModuleMapError(
                f"{where}: ends at 0x{offset + size:x}, past the module's "
                f"0x{span:x} bytes"
            )
        sections.append(SectionRange(name=name, offset=offset, size=size))

    placements: list[Placement] = []
    for entry in body.get("text_placement", body.get("placements", [])):
        where = f"{origin}: text_placement"
        record = _mapping(entry, where=where)
        obj = record.get("object")
        if not isinstance(obj, str) or not obj.strip():
            raise ModuleMapError(f"{where}: every entry needs an 'object' path")
        section = str(record.get("section", ".text"))
        offset = _integer(record.get("offset", 0), where=f"{where} {obj} offset")
        extent = (
            None
            if record.get("size") is None
            else _integer(record["size"], where=f"{where} {obj} size")
        )
        placement = Placement(object=obj, section=section, offset=offset, size=extent)
        owner = next((item for item in sections if item.name == section), None)
        if owner is not None:
            end = placement.end if placement.end is not None else offset + 1
            if not owner.contains(offset, max(end - offset, 1)):
                raise ModuleMapError(
                    f"{where}: {obj} at 0x{offset:x} is outside section "
                    f"{section!r} (0x{owner.offset:x}..0x{owner.end:x})"
                )
        placements.append(placement)

    table_sites: list[TableSite] = []
    for entry in body.get("relocation_sites", []):
        where = f"{origin}: relocation_sites"
        if isinstance(entry, Mapping):
            offset = _integer(entry.get("offset"), where=where)
            raw_type = entry.get("type")
            site_type = None if raw_type is None else _reloc_type(raw_type, where=where)
        else:
            offset = _integer(entry, where=where)
            site_type = None
        table_sites.append(TableSite(offset=offset, type=site_type))

    alias_template = body.get("alias_template")
    if alias_template is not None and not isinstance(alias_template, str):
        raise ModuleMapError(f"{origin}: alias_template must be a string")

    return ModuleMap(
        name=str(body.get("name", "module")),
        image_start=image_start,
        image_end=image_end,
        synthetic_vma=_integer(
            body.get("synthetic_vma", 0), where=f"{origin}: synthetic_vma"
        ),
        sections=tuple(sections),
        placements=tuple(placements),
        table_sites=tuple(table_sites),
        alias_template=alias_template,
    )


_TYPE_NUMBERS = {
    "R_MIPS_32": R_MIPS_32,
    "R_MIPS_26": R_MIPS_26,
    "R_MIPS_HI16": R_MIPS_HI16,
    "R_MIPS_LO16": R_MIPS_LO16,
}


def _reloc_type(value: Any, *, where: str) -> int:
    if isinstance(value, str):
        name = value.strip().upper()
        if name in _TYPE_NUMBERS:
            return _TYPE_NUMBERS[name]
        return _integer(value, where=where)
    return _integer(value, where=where)


# ---------------------------------------------------------------------------
# Sites and values
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Site:
    """One relocation site, mapped from an object offset into the image."""

    symbol: str
    object: str
    section: str
    object_offset: int
    type: int
    module_offset: int | None = None
    image_offset: int | None = None
    stored: int | None = None
    object_addend: int | None = None
    in_table: bool | None = None
    note: str = ""

    @property
    def kind(self) -> str:
        return r_mips_name(self.type)

    @property
    def mapped(self) -> bool:
        return self.stored is not None and self.object_addend is not None

    def as_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "object": self.object,
            "section": self.section,
            "object_offset": self.object_offset,
            "type": self.type,
            "kind": self.kind,
            "module_offset": self.module_offset,
            "image_offset": self.image_offset,
            "stored": self.stored,
            "object_addend": self.object_addend,
            "in_table": self.in_table,
            "note": self.note,
        }


@dataclass(frozen=True)
class SymbolValue:
    """One placeholder symbol and the value every one of its sites demands."""

    name: str
    value: int
    sites: tuple[Site, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "value": self.value,
            "sites": [site.as_dict() for site in self.sites],
        }


@dataclass(frozen=True)
class Conflict:
    """A symbol the synthesis refuses, and exactly why."""

    symbol: str
    reason: str
    detail: str = ""
    values: tuple[int, ...] = ()
    sites: tuple[Site, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "reason": self.reason,
            "detail": self.detail,
            "values": list(self.values),
            "sites": [site.as_dict() for site in self.sites],
        }


@dataclass(frozen=True)
class Alias:
    """One generated-identity alias: `identity = friendly_name;`."""

    identity: str
    name: str
    object: str
    module_offset: int

    def as_dict(self) -> dict[str, Any]:
        return {
            "identity": self.identity,
            "name": self.name,
            "object": self.object,
            "module_offset": self.module_offset,
        }


@dataclass(frozen=True)
class RelocSurface:
    """Everything one run of the synthesis found."""

    module: str
    objects: tuple[str, ...] = ()
    sites: tuple[Site, ...] = ()
    values: tuple[SymbolValue, ...] = ()
    conflicts: tuple[Conflict, ...] = ()
    aliases: tuple[Alias, ...] = ()
    #: Whether a shipped relocation table was supplied to corroborate sites.
    corroborated: bool = False
    warnings: tuple[str, ...] = ()

    @property
    def ok(self) -> bool:
        return not self.conflicts

    def value_map(self) -> dict[str, int]:
        return {item.name: item.value for item in self.values}

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": SURFACE_SCHEMA,
            "module": self.module,
            "objects": list(self.objects),
            "corroborated": self.corroborated,
            "values": [item.as_dict() for item in self.values],
            "conflicts": [item.as_dict() for item in self.conflicts],
            "aliases": [item.as_dict() for item in self.aliases],
            "sites": [site.as_dict() for site in self.sites],
            "warnings": list(self.warnings),
            "ok": self.ok,
        }


def sext16(value: int) -> int:
    """Sign-extend a 16-bit field, the way the LO16 half of a pair is read."""

    return value - 0x10000 if value & 0x8000 else value


def stored_field(data: bytes, offset: int, r_type: int) -> int | None:
    """Return the relocation's stored field from the word at ``offset``."""

    if offset < 0 or offset + 4 > len(data):
        return None
    word = struct.unpack_from(">I", data, offset)[0]
    if r_type == R_MIPS_26:
        return int(word & 0x03FFFFFF)
    if r_type in (R_MIPS_HI16, R_MIPS_LO16):
        return int(word & 0xFFFF)
    return int(word)


def _pairs(sites: Sequence[Site]) -> list[tuple[Site | None, Site | None]]:
    """Attach each ``R_MIPS_HI16`` to its matching ``R_MIPS_LO16``.

    Compilers emit the pair in order against the same symbol, which is the
    MIPS REL convention the linker itself relies on. Pairing matters because a
    HI16's stored field is only meaningful together with the sign of its LO16.
    """

    pending: dict[str, list[Site]] = defaultdict(list)
    out: list[tuple[Site | None, Site | None]] = []
    for site in sites:
        if site.type == R_MIPS_HI16:
            pending[site.symbol].append(site)
        elif site.type == R_MIPS_LO16:
            his = pending.pop(site.symbol, [])
            if his:
                out.extend((high, site) for high in his)
            else:
                out.append((None, site))
        else:
            out.append((site, None))
    for group in pending.values():
        out.extend((high, None) for high in group)
    return out


def _required_value(high: Site | None, low: Site | None, vma: int) -> int | None:
    """The linker value the pair (or lone site) demands, or None if unreadable."""

    anchor = high or low
    if anchor is None:
        return None
    for site in (high, low):
        if site is not None and (site.stored is None or site.object_addend is None):
            return None
    if high is not None and low is not None and high.type == R_MIPS_HI16:
        assert high.stored is not None and low.stored is not None
        assert high.object_addend is not None and low.object_addend is not None
        target = (high.stored << 16) + sext16(low.stored)
        have = (high.object_addend << 16) + sext16(low.object_addend)
    else:
        assert anchor.stored is not None and anchor.object_addend is not None
        if anchor.type == R_MIPS_26:
            # A `jal` field is 28 bits and the hardware supplies the rest
            # from `PC & 0xF0000000`, so only the VMA's top nibble belongs
            # in the value. OR-ing the whole VMA bleeds a real load address'
            # lower bits into the immediate and relinks to a different word.
            target = (vma & 0xF0000000) | (anchor.stored << 2)
            have = anchor.object_addend << 2
        elif anchor.type == R_MIPS_32:
            target, have = anchor.stored, anchor.object_addend
        elif anchor.type == R_MIPS_HI16:
            target, have = anchor.stored << 16, anchor.object_addend << 16
        else:
            target, have = sext16(anchor.stored), sext16(anchor.object_addend)
    return (target - have) & 0xFFFFFFFF


def module_defined_names(
    objects: Sequence[tuple[str, ElfObject]], sections: Iterable[str] = (".text",)
) -> set[str]:
    """Names defined in the module's own placed sections, across its objects.

    A reference to one of those needs no assignment: an intra-module call is
    resolved by the module's own layout, and the assembler already emits the
    shipped word for it at the synthetic VMA. Every other referenced symbol --
    another module's function, a resident function, or this module's own data
    that the runtime places separately -- must carry the stored addend instead
    of whatever address this build happens to give it.

    Only a *linkable* definition counts. A `STB_LOCAL` symbol resolves nothing
    outside the object that defines it, so a static in a sibling object is not
    the module's definition of that name: dropping the value line for it would
    leave the link with an undefined reference and no reason for it.
    """

    wanted = set(sections)
    out: set[str] = set()
    for _name, elf in objects:
        indices = {section.index for section in elf.sections if section.name in wanted}
        for symbol in elf.symbols:
            if not symbol.name or symbol.shndx not in indices:
                continue
            if symbol.bind in LINKABLE_BINDINGS:
                out.add(symbol.name)
    return out


def collect_sites(
    elf: ElfObject,
    module: ModuleMap,
    image: bytes,
    *,
    object_name: str,
    skip: Iterable[str] = (),
) -> tuple[list[Site], list[str]]:
    """Map every relocation in this object's placed sections into the image."""

    skipped = set(skip)
    warnings: list[str] = []
    placements = module.placements_for(object_name)
    if not placements:
        warnings.append(
            f"{object_name}: the module map places no section of this object; "
            "no site can be mapped into the image"
        )
        return [], warnings

    table: dict[int, list[TableSite]] = defaultdict(list)
    for entry in module.table_sites:
        table[entry.offset].append(entry)

    sites: list[Site] = []
    for placement in placements:
        section_bytes = elf.section_bytes(placement.section)
        if section_bytes is None:
            warnings.append(
                f"{object_name}: the map places {placement.section} but the "
                "object has no such section"
            )
            continue
        section_header = elf.section(placement.section)
        own_index = None if section_header is None else section_header.index
        relocations: tuple[Reloc, ...] = elf.relocations_for(placement.section)
        for reloc in relocations:
            symbol = elf.symbol(reloc.sym_index)
            name = symbol.name if symbol is not None else ""
            if not name or name in skipped:
                continue
            if (
                symbol is not None
                and symbol.shndx != SHN_UNDEF
                and symbol.shndx == own_index
            ):
                # Defined in this object's own placed section: intra-module,
                # already correct at the synthetic VMA.
                continue
            module_offset = placement.offset + reloc.offset
            image_offset = module.image_offset(module_offset)
            site = Site(
                symbol=name,
                object=object_name,
                section=placement.section,
                object_offset=reloc.offset,
                type=reloc.type,
                module_offset=module_offset,
                image_offset=image_offset,
            )
            if reloc.type not in SUPPORTED_TYPES:
                sites.append(
                    _noted(site, f"unsupported relocation {r_mips_name(reloc.type)}")
                )
                continue
            # A map may name its sections `.text` or `text`; both spellings
            # occur in real project configuration and neither is worth
            # refusing a whole module over.
            owner = module.section(placement.section) or module.section(
                placement.section.lstrip(".")
            )
            if owner is not None and not owner.contains(module_offset, 4):
                sites.append(_noted(site, "outside the module section"))
                continue
            if not module.image_start <= image_offset < module.image_end:
                sites.append(_noted(site, "outside the module's image range"))
                continue
            stored = stored_field(image, image_offset, reloc.type)
            addend = stored_field(section_bytes, reloc.offset, reloc.type)
            if stored is None or addend is None:
                sites.append(_noted(site, "unmapped"))
                continue
            matches = table.get(module_offset, [])
            in_table: bool | None = None
            if module.table_sites:
                in_table = any(
                    entry.type is None or entry.type == reloc.type for entry in matches
                )
            sites.append(
                Site(
                    symbol=name,
                    object=object_name,
                    section=placement.section,
                    object_offset=reloc.offset,
                    type=reloc.type,
                    module_offset=module_offset,
                    image_offset=image_offset,
                    stored=stored,
                    object_addend=addend,
                    in_table=in_table,
                )
            )
    return sites, warnings


def _noted(site: Site, note: str) -> Site:
    return Site(
        symbol=site.symbol,
        object=site.object,
        section=site.section,
        object_offset=site.object_offset,
        type=site.type,
        module_offset=site.module_offset,
        image_offset=site.image_offset,
        note=note,
    )


def solve(
    sites: Sequence[Site], module: ModuleMap
) -> tuple[list[SymbolValue], list[Conflict]]:
    """Reduce mapped sites to one value per symbol, or a stated refusal.

    Two independent refusals live here. A symbol whose sites demand different
    values has **diverged at the site**: the candidate's own instructions
    differ where the placeholder is referenced, so no addend is readable and
    inventing one would silently corrupt the link. A symbol every one of whose
    corroborated sites was filtered away is not "fine" either -- it means the
    shipped table names the symbol somewhere, but not at any site this object
    still spells the same way.
    """

    by_object: dict[tuple[str, str], list[Site]] = defaultdict(list)
    for site in sites:
        by_object[(site.object, site.section)].append(site)

    # A site the module's own relocation table does not name is not a
    # relocation site in the shipped image: reading an addend there reads an
    # instruction word. When any site for a symbol *is* corroborated, ignore
    # the ones that are not -- that is the image's own statement, not a
    # heuristic, and it is what makes the procedure tolerant of a candidate
    # whose schedule diverges away from the sites in question.
    corroborated = {site.symbol for site in sites if site.in_table}

    wanted: dict[str, dict[int, list[Site]]] = defaultdict(lambda: defaultdict(list))
    unreadable: dict[str, list[Site]] = defaultdict(list)
    for group in by_object.values():
        for high, low in _pairs(group):
            anchor = high or low
            if anchor is None:
                continue
            members = tuple(site for site in (high, low) if site is not None)
            name = anchor.symbol
            if name in corroborated and not all(site.in_table for site in members):
                continue
            if any(not site.mapped for site in members):
                unreadable[name].extend(members)
                continue
            value = _required_value(high, low, module.synthetic_vma)
            if value is None:
                unreadable[name].extend(members)
                continue
            wanted[name][value].extend(members)

    values: list[SymbolValue] = []
    conflicts: list[Conflict] = []
    seen = {site.symbol for site in sites}
    for name in sorted(seen - set(wanted) - set(unreadable)):
        conflicts.append(
            Conflict(
                symbol=name,
                reason="no-corroborated-site",
                detail=(
                    "the shipped relocation table names this symbol, but not "
                    "at any site this object still spells the same way: the "
                    "schedule diverges at every corroborated site"
                ),
                sites=tuple(site for site in sites if site.symbol == name),
            )
        )
    for name in sorted(wanted):
        candidates = wanted[name]
        if len(candidates) == 1:
            value, agreeing = next(iter(candidates.items()))
            values.append(SymbolValue(name=name, value=value, sites=tuple(agreeing)))
            continue
        conflicts.append(
            Conflict(
                symbol=name,
                reason="schedule-divergence-at-site",
                detail=(
                    f"{len(candidates)} distinct values across "
                    f"{sum(len(group) for group in candidates.values())} site(s): "
                    + ", ".join(f"0x{value:08x}" for value in sorted(candidates))
                ),
                values=tuple(sorted(candidates)),
                sites=tuple(site for group in candidates.values() for site in group),
            )
        )
    for name in sorted(unreadable):
        if name in wanted:
            continue
        conflicts.append(
            Conflict(
                symbol=name,
                reason="unmapped-site",
                detail="no site of this symbol could be read from the image",
                sites=tuple(unreadable[name]),
            )
        )
    return values, sorted(conflicts, key=lambda item: item.symbol)


def unpaired_hi16(sites: Sequence[Site]) -> tuple[str, ...]:
    """Symbols whose value rests on an ``R_MIPS_HI16`` with no ``R_MIPS_LO16``.

    The HI16 field a linker writes is ``((V + 0x8000) >> 16) & 0xFFFF``: the
    borrow it carries is the sign of the LO16 half, and a HI16 with no LO16
    site cannot observe it. Every value in a 64 KiB window writes the same
    word, so the one this module picks is right *for the link* and
    non-canonical as a number. That is ambiguity to expose, not to hide.
    """

    by_object: dict[tuple[str, str], list[Site]] = defaultdict(list)
    for site in sites:
        by_object[(site.object, site.section)].append(site)
    out: set[str] = set()
    for group in by_object.values():
        for high, low in _pairs(group):
            if low is None and high is not None and high.type == R_MIPS_HI16:
                out.add(high.symbol)
    return tuple(sorted(out))


def object_aliases(
    elf: ElfObject, module: ModuleMap, *, object_name: str
) -> list[Alias]:
    """Generated-identity aliases for the global functions this object defines.

    The identity is whatever the host's extraction tool names a module offset;
    ``alias_template`` in the module map spells it, with ``module``,
    ``module_offset``, ``image_offset`` and ``vma`` available as fields. Only
    global function symbols matter: a static is not linkable, and a name that
    already *is* its identity needs no alias -- that assignment is circular.
    """

    if not module.alias_template:
        return []
    out: list[Alias] = []
    for placement in module.placements_for(object_name):
        section = elf.section(placement.section)
        if section is None:
            continue
        for symbol in elf.symbols:
            if symbol.shndx != section.index or not symbol.name:
                continue
            if symbol.bind != STB_GLOBAL or symbol.type != STT_FUNC:
                continue
            module_offset = placement.offset + symbol.value
            identity = module.alias_template.format(
                module=module.name,
                module_offset=module_offset,
                image_offset=module.image_offset(module_offset),
                vma=module.synthetic_vma + module_offset,
            )
            if identity == symbol.name:
                continue
            out.append(
                Alias(
                    identity=identity,
                    name=symbol.name,
                    object=object_name,
                    module_offset=module_offset,
                )
            )
    return out


def synthesize(
    objects: Sequence[tuple[str, ElfObject]],
    module: ModuleMap,
    image: bytes,
    *,
    local_sections: Iterable[str] = (".text",),
) -> RelocSurface:
    """Synthesize the whole surface for one module from its objects.

    ``objects`` is ``(name, parsed object)`` for every object of the module the
    link consumes. Passing them together is what lets an intra-module reference
    be recognized as one: a symbol another object of this same module defines
    needs no assignment at all.
    """

    local = module_defined_names(objects, local_sections)
    all_sites: list[Site] = []
    warnings: list[str] = []
    aliases: list[Alias] = []
    for name, elf in objects:
        sites, object_warnings = collect_sites(
            elf, module, image, object_name=name, skip=local
        )
        all_sites.extend(sites)
        warnings.extend(object_warnings)
        aliases.extend(object_aliases(elf, module, object_name=name))
    values, conflicts = solve(all_sites, module)

    # An identity that an alias line *defines* must not also get a value line:
    # the linker takes the last assignment and the shadowed one is invisible.
    aliased = {item.identity for item in aliases}
    shadowed = sorted({item.name for item in values} & aliased)
    if shadowed:
        values = [item for item in values if item.name not in aliased]
        warnings.append(
            "dropped "
            + str(len(shadowed))
            + " value line(s) an alias already defines: "
            + ", ".join(shadowed)
        )
    orphans = [
        name
        for name in unpaired_hi16(all_sites)
        if name in {item.name for item in values}
    ]
    if orphans:
        warnings.append(
            "value(s) resting on an R_MIPS_HI16 with no R_MIPS_LO16 site, "
            "whose low half is unobserved: any value in the same 64 KiB "
            "window writes the same word, so these are right for the link "
            "and non-canonical as numbers: " + ", ".join(orphans)
        )
    if not module.table_sites:
        warnings.append(
            "no shipped relocation table was supplied: every site is trusted "
            "as a relocation site, so a literal the runtime does not patch "
            "cannot be told apart from an addend"
        )
    return RelocSurface(
        module=module.name,
        objects=tuple(name for name, _elf in objects),
        sites=tuple(all_sites),
        values=tuple(values),
        conflicts=tuple(conflicts),
        aliases=tuple(aliases),
        corroborated=bool(module.table_sites),
        warnings=tuple(warnings),
    )


# ---------------------------------------------------------------------------
# Rendering and audit
# ---------------------------------------------------------------------------


def render_linker_block(surface: RelocSurface, *, header: bool = True) -> list[str]:
    """Render the surface as a linker symbol block plus an alias block."""

    lines: list[str] = []
    if header:
        lines += [
            "/*",
            " * Generated by `decomp-workbench reloc-surface` -- do not edit by hand.",
            f" * Module {surface.module}, {len(surface.objects)} object(s).",
            " */",
            "",
        ]
    lines.append("/* Stored relocation addends, per translation unit. */")
    by_object: dict[str, list[SymbolValue]] = defaultdict(list)
    for item in surface.values:
        origin = item.sites[0].object if item.sites else ""
        by_object[origin].append(item)
    for origin in sorted(by_object):
        lines.append("")
        lines.append(f"/* {origin} */")
        for item in sorted(by_object[origin], key=lambda entry: entry.name):
            lines.append(f"{item.name} = 0x{item.value:08X};")
    if surface.aliases:
        lines.append("")
        lines.append("/* Generated identities for adopted names. */")
        by_alias: dict[str, list[Alias]] = defaultdict(list)
        for alias in surface.aliases:
            by_alias[alias.object].append(alias)
        for origin in sorted(by_alias):
            lines.append("")
            lines.append(f"/* {origin} */")
            for alias in sorted(by_alias[origin], key=lambda entry: entry.identity):
                lines.append(f"{alias.identity} = {alias.name};")
    for conflict in surface.conflicts:
        lines.append(f"/* UNRESOLVED {conflict.symbol}: {conflict.reason} */")
    return lines


def parse_linker_block(text: str) -> dict[str, str]:
    """Read `NAME = VALUE;` assignments back out of a linker symbol block.

    Later assignments win, because that is what the linker does with a file
    that assigns one name twice -- an audit that disagreed with the linker
    about which line is live would be auditing a file nobody links.
    """

    out: dict[str, str] = {}
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith(("/*", "*", "//")):
            continue
        match = ASSIGNMENT_RE.match(line)
        if match is not None:
            out[match.group("name")] = match.group("value").strip()
    return out


def tracked_values(text: str) -> dict[str, int]:
    """The numeric half of :func:`parse_linker_block`: name -> value."""

    out: dict[str, int] = {}
    for name, value in parse_linker_block(text).items():
        try:
            out[name] = int(value, 0)
        except ValueError:
            continue
    return out


@dataclass(frozen=True)
class AuditRow:
    name: str
    status: str
    tracked: int | None = None
    synthesized: int | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "status": self.status,
            "tracked": self.tracked,
            "synthesized": self.synthesized,
        }


@dataclass(frozen=True)
class AuditReport:
    """A replay of a hand-written block against the synthesized surface."""

    rows: tuple[AuditRow, ...] = ()
    conflicts: tuple[Conflict, ...] = ()

    def count(self, status: str) -> int:
        return sum(1 for row in self.rows if row.status == status)

    @property
    def agree(self) -> int:
        return self.count("agree")

    @property
    def disagree(self) -> int:
        return self.count("disagree")

    @property
    def compared(self) -> int:
        return self.agree + self.disagree

    @property
    def ok(self) -> bool:
        return self.disagree == 0 and not self.conflicts

    def as_dict(self) -> dict[str, Any]:
        return {
            "agree": self.agree,
            "disagree": self.disagree,
            "compared": self.compared,
            "untracked": self.count("untracked"),
            "unreproduced": self.count("unreproduced"),
            "rows": [row.as_dict() for row in self.rows],
            "conflicts": [item.as_dict() for item in self.conflicts],
            "ok": self.ok,
        }


def audit(surface: RelocSurface, tracked: Mapping[str, int]) -> AuditReport:
    """Score the synthesized values against an existing hand-written block.

    Four outcomes, and the last two are as informative as the first two: a
    name the block does not carry (``untracked``) is one the link defines by
    other means, and a name the synthesis did not reach (``unreproduced``) is
    where the procedure stops rather than where the block is wrong.
    """

    synthesized = surface.value_map()
    rows: list[AuditRow] = []
    for name in sorted(set(tracked) | set(synthesized)):
        if name in tracked and name in synthesized:
            same = tracked[name] == synthesized[name]
            rows.append(
                AuditRow(
                    name=name,
                    status="agree" if same else "disagree",
                    tracked=tracked[name],
                    synthesized=synthesized[name],
                )
            )
        elif name in synthesized:
            rows.append(
                AuditRow(name=name, status="untracked", synthesized=synthesized[name])
            )
        else:
            rows.append(
                AuditRow(name=name, status="unreproduced", tracked=tracked[name])
            )
    return AuditReport(rows=tuple(rows), conflicts=surface.conflicts)


# ---------------------------------------------------------------------------
# The permuter's precondition
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PlaceholderFinding:
    """Whether a scratch can reproduce the target's own call relocations.

    The permuter scores a scratch object against the target's words. For a
    function in an unrelocated module the target spells every call with a
    placeholder the scratch has no way to name, so identical instructions
    still score as mismatches and the search can never reach zero. That is a
    property of the oracle, not of the function.
    """

    function: str
    call_sites: int = 0
    self_named: tuple[str, ...] = ()
    absent_from_candidate: tuple[str, ...] = ()
    reproducible: tuple[str, ...] = ()
    #: Whether a candidate object was supplied. Without one a self-named site
    #: is indistinguishable from ordinary self-recursion, and the message says
    #: so rather than asserting a floor nobody measured.
    candidate_read: bool = False

    @property
    def unreproducible(self) -> tuple[str, ...]:
        return tuple(sorted(set(self.self_named) | set(self.absent_from_candidate)))

    @property
    def blocked(self) -> bool:
        """True when *every* call site names something the scratch cannot."""

        return bool(self.call_sites) and not self.reproducible

    @property
    def message(self) -> str:
        names = ", ".join(self.unreproducible[:3])
        text = (
            f"every R_MIPS_26 site in the target ({self.call_sites}) names a "
            f"symbol this scratch cannot reproduce ({names}); the permuter "
            "score cannot reach zero for this function however good the C is "
            "-- use `decomp-workbench linked-compare` against the linked "
            "image instead"
        )
        if self.self_named and not self.candidate_read:
            text += (
                "; a self-named site also reads as ordinary self-recursion, "
                "which `--candidate-object` tells apart"
            )
        return text

    def as_dict(self) -> dict[str, Any]:
        return {
            "function": self.function,
            "call_sites": self.call_sites,
            "self_named": list(self.self_named),
            "absent_from_candidate": list(self.absent_from_candidate),
            "reproducible": list(self.reproducible),
            "unreproducible": list(self.unreproducible),
            "candidate_read": self.candidate_read,
            "blocked": self.blocked,
        }


def _function_range(
    elf: ElfObject, function: str, section: str
) -> tuple[int, int] | None:
    header = elf.section(section)
    if header is None:
        return None
    for symbol in elf.symbols:
        if symbol.name == function and symbol.shndx == header.index:
            size = symbol.size or (header.size - symbol.value)
            return symbol.value, symbol.value + size
    return None


def placeholder_call_check(
    target: ElfObject,
    candidate: ElfObject | None,
    *,
    function: str,
    section: str = ".text",
) -> PlaceholderFinding:
    """Classify the target's call relocations by whether a scratch can name them.

    A call site is unreproducible when it names a symbol the candidate object
    does not carry, or -- for want of a candidate to check against -- when it
    names the function itself, the shape an unrelocated module's self-relative
    jump table has, where the placeholder *is* the containing symbol.

    The candidate is checked first, and that order is the whole difference
    between this and a heuristic. An ordinary resident function that recurses
    spells its own call with the containing symbol too, so the name alone
    cannot tell the two apart; a candidate that carries the symbol can
    reproduce the word, whichever shape it is.
    """

    window = _function_range(target, function, section)
    names: list[str] = []
    for reloc in target.relocations_for(section):
        if reloc.type != R_MIPS_26:
            continue
        if window is not None and not window[0] <= reloc.offset < window[1]:
            continue
        symbol = target.symbol(reloc.sym_index)
        if symbol is not None and symbol.name:
            names.append(symbol.name)

    candidate_names = (
        {symbol.name for symbol in candidate.symbols if symbol.name}
        if candidate is not None
        else set()
    )
    self_named: set[str] = set()
    absent: set[str] = set()
    reproducible: set[str] = set()
    for name in names:
        if candidate is not None and name in candidate_names:
            reproducible.add(name)
        elif name == function:
            self_named.add(name)
        elif candidate is not None:
            absent.add(name)
        else:
            reproducible.add(name)
    return PlaceholderFinding(
        function=function,
        call_sites=len(names),
        self_named=tuple(sorted(self_named)),
        absent_from_candidate=tuple(sorted(absent)),
        reproducible=tuple(sorted(reproducible)),
        candidate_read=candidate is not None,
    )


__all__ = [
    "MODULE_MAP_SCHEMA",
    "SURFACE_SCHEMA",
    "Alias",
    "AuditReport",
    "AuditRow",
    "Conflict",
    "ModuleMap",
    "ModuleMapError",
    "PlaceholderFinding",
    "Placement",
    "RelocSurface",
    "SectionRange",
    "Site",
    "SymbolValue",
    "TableSite",
    "audit",
    "collect_sites",
    "module_defined_names",
    "object_aliases",
    "parse_linker_block",
    "parse_module_map",
    "placeholder_call_check",
    "render_linker_block",
    "sext16",
    "solve",
    "stored_field",
    "synthesize",
    "tracked_values",
    "unpaired_hi16",
]
